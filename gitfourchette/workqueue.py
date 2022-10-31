# Based on https://www.learnpyqt.com/courses/concurrent-execution/multithreading-pyqt-applications-qthreadpool/
from gitfourchette import log
from gitfourchette import settings
from gitfourchette.globalstatus import globalstatus
from gitfourchette.qt import *
from gitfourchette.util import excMessageBox, onAppThread
from typing import Callable


class WorkerSignals(QObject):
    """
    Defines the signals available from a running worker thread.

    Supported signals are:

    finished
        No data

    error
        BaseException object

    result
        `object` data returned from processing, anything
    """
    finished = Signal()
    error = Signal(object)
    result = Signal(object)


class Worker(QRunnable):
    """
    Worker thread

    Inherits from QRunnable to handler worker thread setup, signals and wrap-up.

    :param callback: The function callback to run on this worker thread. Supplied args and
                     kwargs will be passed through to the runner.
    :type callback: function
    :param args: Arguments to pass to the callback function
    :param kwargs: Keywords to pass to the callback function

    """

    def __init__(self, parent: QObject, name: str, fn, *args, **kwargs):
        super().__init__()

        self.name = name  # for debugging
        self.fn = fn
        self.args = args
        self.kwargs = kwargs

        self.signals = WorkerSignals(parent)

        self.setAutoDelete(True)

    def __del__(self):
        log.info("workqueue", F"Worker destroyed: {self.name}")

    def run(self):
        """
        Initialize the runner function with passed args, kwargs.
        """

        # Retrieve args/kwargs here; and fire processing using them
        try:
            result = self.fn(*self.args, **self.kwargs)
        except BaseException as exc:
            self.signals.error.emit(exc)
        else:
            self.signals.result.emit(result)  # Return the result of the processing
        finally:
            self.signals.finished.emit()  # Done
            self.signals.deleteLater()  # Tell Qt we're done with that QObject


class WorkQueue(QObject):
    def __init__(self, parent, maxThreadCount=1):
        super().__init__(parent)
        self.setObjectName("WorkQueue")
        self.threadpool = QThreadPool(parent)
        self.threadpool.setMaxThreadCount(maxThreadCount)
        self.mutex = QMutex()

    def put(
            self,
            work: Callable[[], object],
            then: Callable[[object], None] = None,
            caption: str = "UnnamedTask",
            priority: int = 0,
            errorCallback: Callable[[BaseException], None] = None):
        """
        Starts a worker thread in the background, especially to perform
        long operations on the repository.

        Only one worker may be running at once; and only one worker may be
        queued at a time.

        :param work: Function to run asynchronously. Returns an object.

        :param then: Completion callback to run on the GUI thread when
        ``work`` is complete. Takes the object returned by ``work`` as its
        input parameter.

        :param caption: Shown in status.

        :param priority: Integer value passed on to `QThreadPool.start()`.

        :param errorCallback: Callback to run on the GUI thread if ``work``
        aborts due to an error. If None, an exception dialog is shown.
        """

        if settings.TEST_MODE:
            self.putSerial(work, then, caption, errorCallback)
        else:
            self.putAsync(work, then, caption, priority, errorCallback)

    def putSerial(self, work, then, caption, errorCallback):
        try:
            result = work()
            if then is not None:
                then(result)
        except BaseException as exc:
            if errorCallback:
                errorCallback(exc)
            else:
                message = self.tr("Operation failed: {0}.").format(caption)
                excMessageBox(exc, title=caption, message=message, parent=self.parent)

    def putAsync(self, work, then, caption, priority, errorCallback):
        def workWrapper():
            assert not onAppThread()
            with QMutexLocker(self.mutex):
                return work()

        # This callback gets executed when the worker's async function has completed successfully.
        def thenWrapper(o):
            assert onAppThread()
            # Clear status caption _before_ running onComplete,
            # because onComplete may start another worker that sets status.
            globalstatus.clearIndeterminateProgressCaption()
            # Finally run completion
            if then is not None:
                then(o)

        if not errorCallback:
            def errorCallback(exc: BaseException):
                message = self.tr("Operation failed: {0}.").format(caption)
                excMessageBox(exc, title=caption, message=message, parent=self.parent)

        w = Worker(self, caption, workWrapper)
        w.signals.result.connect(thenWrapper)
        w.signals.error.connect(lambda: globalstatus.clearIndeterminateProgressCaption())
        w.signals.error.connect(errorCallback)
        globalstatus.setIndeterminateProgressCaption(self.tr("{0}...").format(caption))

        # Remove any pending worker from the queue.
        # TODO: we should prevent the currently-running worker's completion callback from running as well.
        self.threadpool.clear()

        # Queue our worker.
        self.threadpool.start(w, priority)


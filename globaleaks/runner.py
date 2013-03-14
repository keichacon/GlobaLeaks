# -*- encoding: utf-8 -*-
#
# Here is implemented the preApplication and postApplication method
# along the Asynchronous event schedule

import sys

from twisted.application import service, internet, app
from twisted.python.runtime import platformType
from apscheduler.scheduler import Scheduler

from globaleaks.db import createTables
from globaleaks.utils import log, MailException
from globaleaks.settings import GLSetting

# The scheduler is a global variable, because can be used to force execution
__all__ = ['GLAsynchronous']

GLAsynchronous = Scheduler()
log.startLogging()

sys.excepthook = MailException

class GLBaseRunner(app.ApplicationRunner):
    """
    This is a specialized runner that is responsible for starting the specified
    service.
    The purpose of it is to do the equivalent of what would be done with
    launching twistd from command line (daemonizing the process, creating the
    PID file, etc).
    """
    def preApplication(self):
        """
        We don't actually want to override this method since there is nothing
        interesting to do in here.
        """
        log.debug("[D] %s %s " % (__file__, __name__), "Class GLBaseRunner", "preApplication")

    def postApplication(self):
        """
        We must place all the operations to be done before the starting of the
        application.
        Here we will take care of the launching of the reactor and the
        operations to be done after it's shutdown.
        """
        log.debug("[D] %s %s " % (__file__, __name__), "Class GLBaseRunner", "postApplication")


def startAsynchronous():
    """
    Initialize the asynchronous operation, scheduled in the system
    https://github.com/globaleaks/GLBackend/wiki/Asynchronous-and-synchronous-operations

    This method would be likely put in GLBaseRunner.postApplication, but is not executed by
    startglobaleaks.runApp, then is called by the OS-depenedent runner below
    """
    from globaleaks.jobs import notification_sched, statistics_sched, \
        delivery_sched, cleaning_sched

    # When the application boot, maybe because has been after a restart, then
    # with the method *.force_execution, we reschedule the execution of all the
    # operations -- TODO, maybe refactored along the scheduler review in TODO

    StatsSched = statistics_sched.APSStatistics()
    StatsSched.force_execution(GLAsynchronous, seconds=8)
    GLAsynchronous.add_interval_job(StatsSched.operation, 10 )
    # GLAsynchronous.add_interval_job(StatsSched.operation, StatsSched.get_node_delta() )

    DeliverSched = delivery_sched.APSDelivery()
    DeliverSched.force_execution(GLAsynchronous, seconds=1)
    GLAsynchronous.add_interval_job(DeliverSched.operation, seconds=7)

    NotifSched = notification_sched.APSNotification()
    NotifSched.force_execution(GLAsynchronous, seconds=5)
    GLAsynchronous.add_interval_job(NotifSched.operation, minutes=3)

    CleanSched = cleaning_sched.APSCleaning()
    CleanSched.force_execution(GLAsynchronous, seconds=13)
    GLAsynchronous.add_interval_job(CleanSched.operation, hours=6)
    # TODO not hours=6 but CleanSched.get_contexts_policies()

    # start the scheduler
    GLAsynchronous.start()


# System dependent runner (windows and Unix)

if platformType == "win32":

    from twisted.scripts._twistw import ServerOptions, WindowsApplicationRunner

    class GLBaseRunnerWindows(WindowsApplicationRunner):
        """
        This runner is specific to windows.
        """
        def postApplication(self):
            """
            This code is taken directly from the method postApplication of
            WindowsApplicationRunner.
            """
            def runApp(res):
                """
                Start the actual service Application.
                """
                service.IService(self.application).privilegedStartService()
                app.startApplication(self.application, not self.config['no_save'])
                app.startApplication(internet.TimerService(0.1, lambda:None), 0)
                startAsynchronous()

            print "WARNING! Windows is not tested!"
            d = createTables()
            d.addCallback(runApp)

            self.startReactor(None, self.oldstdout, self.oldstderr)
            log.msg("Server Shut Down.")

    GLBaseRunner = GLBaseRunnerWindows

else:
    from twisted.scripts._twistd_unix import ServerOptions, UnixApplicationRunner
    ServerOptions = ServerOptions

    class GLBaseRunnerUnix(UnixApplicationRunner):
        """
        This runner is specific to Unix systems.
        """
        def postApplication(self):
            """
            THis code is taken directly from UnixApplicationRunner
            """
            def runApp(res):
                """
                Start the actual service Application.
                """
                print "Running start."
                try:
                    self.startApplication(self.application)
                except Exception, e:
                    log.err("Network error: %s Use ^C" % e)
                    raise e

                try:
                    startAsynchronous()
                except Exception, e:
                    log.err("Scheduler error: %s Use ^C" % e)
                    raise e

                print "GLBackend is now running"
                print "Visit http://127.0.0.1:%d/index.html to interact with me" % GLSetting.bind_port

            d = createTables()
            d.addCallback(runApp)

            self.startReactor(None, self.oldstdout, self.oldstderr)
            self.removePID(self.config['pidfile'])

    GLBaseRunner = GLBaseRunnerUnix

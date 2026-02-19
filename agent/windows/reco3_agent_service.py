"""RECO3 PC Agent - Windows Service.
Uses pywin32 to run as a Windows service.
"""

import os
import sys

# Add common directory to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'common'))

try:
    import win32serviceutil
    import win32service
    import win32event
    import servicemanager
except ImportError:
    print("ERROR: pywin32 is required. Install with: pip install pywin32")
    sys.exit(1)

from reco_agent import RECOAgent


class RECO3AgentService(win32serviceutil.ServiceFramework):
    _svc_name_ = "RECO3Agent"
    _svc_display_name_ = "RECO3 PC Agent"
    _svc_description_ = "PC monitoring and control agent for RECO3"

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.agent = None

    def SvcDoRun(self):
        """Start the agent service."""
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, ""),
        )

        config_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "common", "config.yaml",
        )

        # Allow override via environment variable
        config_path = os.environ.get("RECO3_AGENT_CONFIG", config_path)

        self.agent = RECOAgent(config_path)
        self.agent.run()

    def SvcStop(self):
        """Stop the agent service."""
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)

        if self.agent:
            self.agent.stop()

        win32event.SetEvent(self.stop_event)

        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STOPPED,
            (self._svc_name_, ""),
        )


if __name__ == "__main__":
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(RECO3AgentService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(RECO3AgentService)

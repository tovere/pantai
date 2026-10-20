"""Install a user launchd service for the dashboard backend and embedded worker."""
import plistlib
import os
import sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
import paper_agent
_, _, key = paper_agent.config()
path=Path.home()/"Library/LaunchAgents/cn.ma-backtest.watch.plist"
path.parent.mkdir(parents=True,exist_ok=True)
payload={"Label":"cn.ma-backtest.watch","ProgramArguments":[sys.executable,"-u",str(root/"watch_server.py")],
         "EnvironmentVariables":{"PAPER_AGENT_API_KEY":key},
         "WorkingDirectory":str(root),"RunAtLoad":True,"KeepAlive":True,
         "ThrottleInterval":15,"StandardOutPath":str(root/"data_cache/watch-service.log"),
         "StandardErrorPath":str(root/"data_cache/watch-service-error.log")}
fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
os.chmod(path,0o600)
with os.fdopen(fd,"wb") as handle: plistlib.dump(payload,handle)
print("Created",path)
print("Existing manually started backend must stop before loading this service.")

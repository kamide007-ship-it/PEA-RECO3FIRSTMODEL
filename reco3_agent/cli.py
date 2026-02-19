import argparse, json, os
from reco3_agent import daemon
from reco3_agent.state import load_state, reset_state, read_logs
from reco3_agent.analyzer import analyze_human

def main(argv=None):
    p = argparse.ArgumentParser(prog="reco3-agent")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("daemon")
    dsub = d.add_subparsers(dest="daemon_cmd", required=True)
    dstart = dsub.add_parser("start")
    dstart.add_argument("--port", type=int, default=int(os.getenv("RECO3_PROXY_PORT", "8100")))
    dstart.add_argument("--bind", type=str, default=os.getenv("RECO3_PROXY_BIND", "127.0.0.1"))
    dsub.add_parser("stop")
    dsub.add_parser("status")

    s = sub.add_parser("state")
    ssub = s.add_subparsers(dest="state_cmd", required=True)
    ssub.add_parser("show")
    ssub.add_parser("reset")

    lg = sub.add_parser("logs")
    lg.add_argument("--limit", type=int, default=20)

    ck = sub.add_parser("check")
    ck.add_argument("text", type=str)

    args = p.parse_args(argv)

    if args.cmd == "daemon":
        if args.daemon_cmd == "start":
            print(json.dumps(daemon.start(port=args.port, bind=args.bind), ensure_ascii=False))
            return
        if args.daemon_cmd == "stop":
            print(json.dumps(daemon.stop(), ensure_ascii=False))
            return
        if args.daemon_cmd == "status":
            print(json.dumps(daemon.status(), ensure_ascii=False))
            return

    if args.cmd == "state":
        if args.state_cmd == "show":
            print(json.dumps(load_state(), ensure_ascii=False, indent=2))
            return
        if args.state_cmd == "reset":
            reset_state()
            print(json.dumps({"status": "reset"}, ensure_ascii=False))
            return

    if args.cmd == "logs":
        print(json.dumps(read_logs(limit=args.limit), ensure_ascii=False, indent=2))
        return

    if args.cmd == "check":
        st = load_state()
        res = analyze_human(args.text, st)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return

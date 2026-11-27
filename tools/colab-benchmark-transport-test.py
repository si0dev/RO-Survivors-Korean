import importlib.util
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("transport",ROOT/"colab-benchmark-transport.py")
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class TransportTests(unittest.TestCase):
    def simulate(self, replies, launch=(0,"REMOTE_WORKER_LAUNCHED"),limit=200):
        with tempfile.TemporaryDirectory() as tmp:
            log=pathlib.Path(tmp)/"translation.log"
            calls=[];clock=[0];events=[];responses=iter(replies)
            def run(args,timeout):
                calls.append(args)
                if args[0]=="exec":
                    return launch
                status,value=next(responses)
                if status==0:
                    pathlib.Path(args[-1]).write_text(value,encoding="utf-8")
                    return 0,""
                return status,value
            rc=mod.collect([],"session","print('worker')",log,"/tmp/mock-worker",
                run=run,now=lambda:clock[0],pause=lambda n:clock.__setitem__(0,clock[0]+n),
                emit=lambda msg,**kw:events.append(msg),limit=limit)
            return rc,log.read_text(),calls,events

    def test_connection_loss_does_not_restart_worker(self):
        a="BENCHMARK_RESULT={\"id\":\"001\"}\n"
        b=a+"BENCHMARK_DONE\n\nREMOTE_WORKER_EXIT 0\n"
        rc,log,calls,events=self.simulate([(0,a),(1,"Connection was lost."),(0,b)])
        self.assertEqual(rc,0)
        self.assertEqual(log,b)
        self.assertEqual(sum(c[0]=="exec" for c in calls),1)
        self.assertIn("COLAB_TRANSPORT_DOWNLOAD=CONNECTION_LOST attempt=1",events)

    def test_lost_launch_ack_recovers_existing_worker(self):
        rc,log,calls,events=self.simulate([(0,"BENCHMARK_DONE\n\nREMOTE_WORKER_EXIT 0\n")],launch=(1,"Connection was lost."))
        self.assertEqual(rc,0)
        self.assertEqual(sum(c[0]=="exec" for c in calls),1)

    def test_worker_exit_is_not_transport_success(self):
        rc,log,_,events=self.simulate([(0,"partial\n\nREMOTE_WORKER_EXIT 1\n")])
        self.assertEqual(rc,1)
        self.assertIn("COLAB_REMOTE_WORKER_EXIT=1",events)

    def test_transport_failure_preserves_results(self):
        a="BENCHMARK_RESULT={\"id\":\"001\"}\n"
        rc,log,_,events=self.simulate([(0,a)]+[(1,"Session 'session' not found.")]*4)
        self.assertEqual(rc,1)
        self.assertEqual(log,a)
        self.assertIn("COLAB_TRANSPORT_DOWNLOAD=SESSION_GONE attempt=4",events)

    def test_regressed_log_is_rejected(self):
        rc,log,_,events=self.simulate([(0,"first\n"),(0,"different\n")])
        self.assertEqual(rc,1)
        self.assertEqual(log,"first\n")
        self.assertIn("COLAB_TRANSPORT_LOG_REGRESSION",events)

    def test_local_supervisor_reports_real_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            work=pathlib.Path(tmp)/"worker"
            work.mkdir()
            (work/"worker.py").write_text("print('BENCHMARK_DONE',flush=True)\nraise SystemExit(3)\n")
            (work/"supervisor.py").write_text(mod.SUPERVISOR)
            subprocess.run([sys.executable,str(work/"supervisor.py"),str(work)],check=True,timeout=10)
            self.assertIn("REMOTE_WORKER_EXIT 3",(work/"worker.log").read_text())

if __name__=="__main__":
    unittest.main()

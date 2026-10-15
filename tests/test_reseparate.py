import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import soundfile as sf
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import engine

class ReseparateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "giọng cần tách lại.wav"
        t = np.arange(44100) / 44100
        self.audio = np.column_stack([.12*np.sin(2*np.pi*220*t), .09*np.sin(2*np.pi*300*t)]).astype(np.float32)
        sf.write(self.source,self.audio,44100)
        self.before = self.source.read_bytes()
        self.cancel = threading.Event()
    def tearDown(self):
        self.temp.cleanup()
    def process(self, **kwargs):
        return engine.process_file(self.source,self.root/'results','reseparate','wav','cpu',self.cancel,
            lambda *_:None,lambda *_:None,lambda *_:None,**kwargs)
    def test_one_extra_separation_preserves_before_audio_and_source(self):
        with patch.object(engine,'separate_chunks',side_effect=lambda decoded,*a:[decoded,decoded]) as separate:
            outputs=self.process(quality='natural')
        self.assertEqual(separate.call_count,1)
        self.assertEqual(separate.call_args.args[-1].model,'htdemucs_ft')
        self.assertEqual([Path(p).name for p in outputs],['giong_truoc_tach_lai.wav','giong_tach_lai.wav','nhac_tach_lai.wav'])
        self.assertEqual(outputs.state,'complete')
        self.assertTrue(Path(outputs[0]).parent.name.startswith('Tach_lai_'))
        self.assertEqual(self.source.read_bytes(),self.before)
        np.testing.assert_array_equal(sf.read(outputs[0],dtype='int16')[0],sf.read(self.source,dtype='int16')[0])
        report=json.loads((Path(outputs[0]).parent/'ket_qua.json').read_text(encoding='utf-8'))
        self.assertEqual(report['mode'],'reseparate')
        self.assertEqual(report['missing'],[])
    def test_repeated_runs_keep_previous_result_files(self):
        with patch.object(engine,'separate_chunks',side_effect=lambda decoded,*a:[decoded,decoded]):
            first=self.process(); second=self.process()
        self.assertNotEqual(Path(first[0]).parent,Path(second[0]).parent)
        self.assertTrue(all(Path(p).is_file() for p in first+second))
    def test_optional_cleanup_failure_keeps_reseparated_voice_and_before_copy(self):
        with patch.object(engine,'separate_chunks',side_effect=lambda decoded,*a:[decoded,decoded]), \
             patch.object(engine,'check_speech_model'), \
             patch.object(engine,'clean_voice',side_effect=RuntimeError('inference failed')):
            result=self.process(cleanup=12)
        self.assertEqual(result.state,'partial')
        self.assertEqual(len(result),3)
        self.assertTrue(all(Path(p).is_file() for p in result))
        report=json.loads((Path(result[0]).parent/'ket_qua.json').read_text(encoding='utf-8'))
        self.assertEqual(report['missing'],['giong_loc.wav'])
    def test_trial_keeps_prefix_and_duration(self):
        with patch.object(engine,'separate_chunks',side_effect=lambda decoded,*a:[decoded,decoded]):
            result=self.process(preview_seconds=30,preview_start=.5)
        self.assertTrue(Path(result[0]).parent.name.startswith('Thu_30s_Tach_lai_'))
        self.assertAlmostEqual(sf.info(result[1]).duration,.5,places=3)
        self.assertEqual(self.source.read_bytes(),self.before)

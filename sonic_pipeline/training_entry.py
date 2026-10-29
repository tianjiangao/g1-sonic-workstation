"""Pin backbone revision, then execute NVIDIA's unchanged fine-tune launcher."""
import runpy
from sonic_pipeline.settings import GROOT
from gr00t.experiment import experiment
_original_run=experiment.run

def pinned_run(config):
    # Official model config supports this field; no pretrained weights changed.
    config.model.model_revision='9ce19a195e423419c349abfc86fd07178b230561'
    config.training.transformers_trust_remote_code=False
    return _original_run(config)
experiment.run=pinned_run
runpy.run_path(str(GROOT/'gr00t/experiment/launch_finetune.py'),run_name='__main__')

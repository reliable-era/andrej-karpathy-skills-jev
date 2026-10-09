"""Unscored SWE control using the installed grader with scoped Docker hardening.

No host package is modified. Resource/capability adaptation must be frozen and
accepted through positive/negative controls before any campaign reuse.
"""
import json
import sys
from pathlib import Path

from docker.models.containers import ContainerCollection
from swebench.harness import run_evaluation

create = ContainerCollection.create


def safe_create(self, *args, **kwargs):
    kwargs.pop('cap_add', None)
    if kwargs.get('volumes') or kwargs.get('mounts'):
        raise RuntimeError('Unexpected host mount in SWE control')
    kwargs.update(cap_drop=['ALL'], security_opt=['no-new-privileges'],
                  mem_limit='8g', nano_cpus=2_000_000_000, runtime='runc')
    container = create(self, *args, **kwargs)
    container.reload()
    with Path('created_containers.jsonl').open('a') as f:
        json.dump({'name':container.name, 'image_id':container.attrs['Image'],
                   'mounts':container.attrs['Mounts'], 'host_config':{
                       k:container.attrs['HostConfig'].get(k) for k in
                       ['CapAdd','CapDrop','SecurityOpt','Memory','NanoCpus','Runtime']}}, f)
        f.write('\n')
    return container


if __name__ == '__main__':
    dataset, predictions, run_id = sys.argv[1:]
    ContainerCollection.create = safe_create
    run_evaluation.main(dataset_name=dataset, split='test', instance_ids=['pydata__xarray-4966'],
                        predictions_path=predictions, max_workers=1, open_file_limit=4096,
                        run_id=run_id, timeout=1200, rewrite_reports=False, modal=False,
                        report_dir='reports')

#!/usr/bin/env python3
"""Summarize JSONL evaluations without labelling proxy metrics as accuracy."""
import argparse
import json
from collections import defaultdict
from pathlib import Path
import numpy as np
p=argparse.ArgumentParser()
p.add_argument('files',nargs='+')
p.add_argument('--output')
args=p.parse_args()
groups=defaultdict(list)
for name in args.files:
    for line in Path(name).read_text().splitlines():
        value=json.loads(line)
        if value.get('record_type')=='tracking':
            groups[(value['session_id'],value['backend'],value['camera'])].append(value)
summary=[]
for (session,backend,camera),rows in groups.items():
    item={'session':session,'backend':backend,'camera':camera,'samples':len(rows),
          'detected_fraction':sum(x['detected'] for x in rows)/len(rows),
          'loss_events':sum(x['loss_event'] for x in rows),
          'reacquisition_events':sum(x['reacquisition_event'] for x in rows),
          'accuracy_measured':False}
    for field in ('inference_ms','request_ms','frame_age_ms','processing_rate_hz',
                  'mask_iou_proxy','depth_mad_m','depth_delta_m'):
        values=[x[field] for x in rows if x.get(field) is not None]
        item[field]={'median':float(np.median(values)),'p95':float(np.percentile(values,95))} if values else None
    summary.append(item)
text=json.dumps(summary,indent=2)+'\n'
if args.output: Path(args.output).write_text(text)
else: print(text)

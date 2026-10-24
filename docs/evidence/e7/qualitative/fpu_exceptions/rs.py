"""Reset-start testpoints (first stimulus step is a reset step) and first reset row per testpoint."""
import json
EQ = '/tmp/claude-0/-home-user-Veri-Sure/12bb865e-7a51-5506-b55a-e5ac7cf72a4a/scratchpad/eq'
RUNS = ['luna12', 'luna13', 'luna14', 'luna15']
def is_reset_step(step):  # same predicate as specflow.tb.runtime.is_reset_step
    return isinstance(step, dict) and bool(step.get("reset"))
RESET_START = {}
FIRST_RST = {}
for r in RUNS:
    st = json.load(open(f'{EQ}/corpora/{r}/fpu_exceptions/stimulus.json'))['testpoints']
    RESET_START[r] = {t['tp_uid'] for t in st if t['stimulus_steps'] and is_reset_step(t['stimulus_steps'][0])}
    rows = json.load(open(f'{EQ}/stim/{r}/fpu_exceptions.json'))['tps']
    for tp, v in rows.items():
        idx = [i for i, row in enumerate(v['rows']) if row[1] == 1]
        FIRST_RST[(r, tp)] = idx[0] if idx else None
def keep(r, tp, e):
    """edge e of testpoint tp of corpus r is free of carried-over state"""
    return tp in RESET_START[r] and FIRST_RST[(r, tp)] is not None and e > FIRST_RST[(r, tp)]
if __name__ == '__main__':
    for r in RUNS:
        n = len(json.load(open(f'{EQ}/stim/{r}/fpu_exceptions.json'))['tps'])
        bad = [tp for tp in RESET_START[r] if FIRST_RST[(r, tp)] != 0]
        print(r, 'reset-start TPs', len(RESET_START[r]), 'of', n, f'({100*len(RESET_START[r])/n:.1f}%)', 'reset-start but first rst row !=0:', len(bad))

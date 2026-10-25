SINGLE={'luna12.gen2','luna12.gen3','luna12.r0','luna12.final','luna14.gen1','luna14.gen3','luna15.gen1','luna15.gen3'}
ALB={'luna12.gen1','luna12.gen2','luna12.r0','luna12.final','luna13.gen1','luna13.gen2','luna13.r0','luna13.final'}
ALSET={'luna14.r0','luna14.final','luna15.r0','luna15.final','luna12.gen3','luna14.gen2','luna15.gen3'}
W0SET={'luna13.r0','luna13.final','luna14.r0','luna14.final','luna15.gen1','luna15.gen2','luna15.r0','luna14.gen2'}
def habits(d):
    h={'PIPE':['P2'] + ([] if d=='luna15.r0' else ['P3']) + (['P1'] if d in SINGLE else []),
       'FSM':['FSM']}
    if d in ALB: h['AL']=['AL']
    if d in ALSET: h['AL']=['ALS']
    if d in W0SET: h['W0']=['W0']
    return h
GATE={'luna12.gen1','luna12.gen2','luna12.r0','luna12.final','luna13.gen3','luna13.final','luna14.gen2','luna14.gen3','luna14.final','luna15.gen3','luna15.final'}
KEEPSET={'luna13.r0','luna13.final','luna14.final','luna15.gen3'}
def habits2(d):
    h=habits(d)
    h['SLAVE']=['SWC']+(['SW'] if d in GATE else [])
    if d in KEEPSET: h['KEEP']=['KEEP']
    if d=='luna12.final': h['CE0']=['CE0']
    return h

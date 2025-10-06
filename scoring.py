import numpy as np
def reverse_score(val):
    if val is None or (isinstance(val,float) and np.isnan(val)):
        return val
    return 6 - val

def compute_domain_means(responses, mapping, reverse_items):
    domain_means = {}
    for scale, items in mapping.items():
        vals = []
        for i in items:
            v = responses.get(i, None)
            if v is None:
                continue
            if i in reverse_items:
                v = reverse_score(v)
            vals.append(v)
        domain_means[scale] = round(float(np.nanmean(vals)) if vals else np.nan, 2)
    return domain_means

def compute_im_score(responses, im_items, reverse_items):
    vals = []
    for i in im_items:
        v = responses.get(i, None)
        if v is None:
            continue
        if i in reverse_items:
            v = reverse_score(v)
        vals.append(v)
    return round(float(np.nansum(vals)),2) if vals else np.nan

def inconsistency_index(responses, pairs):
    diffs = []
    for a,b in pairs:
        va = responses.get(a,None); vb = responses.get(b,None)
        if va is None or vb is None:
            continue
        diffs.append(abs(va - vb))
    return round(float(np.nanmean(diffs)),3) if diffs else np.nan

def max_longstring(responses):
    seq = [responses.get(i) for i in range(1,61) if responses.get(i) is not None]
    if not seq:
        return 0
    run = 1; max_run = 1
    for i in range(1,len(seq)):
        if seq[i]==seq[i-1]:
            run +=1
            if run>max_run: max_run = run
        else:
            run = 1
    return max_run

def adjust_for_im(domain_scores, im_sum, im_len):
    im_mean = im_sum / im_len if im_len else None
    adj = 0.0
    if im_mean is not None:
        if im_mean >= 3.9:
            adj = -0.3
        elif im_mean <= 2.5:
            adj = 0.3
    adjusted = {}
    for k,v in domain_scores.items():
        if k.lower().startswith('impression') or k.lower().startswith('attention'):
            adjusted[k] = v
            continue
        if v is None or (isinstance(v,float) and np.isnan(v)):
            adjusted[k] = v
            continue
        a = round(min(5.0, max(1.0, v + adj)),2)
        adjusted[k] = a
    return adjusted

import sys,re
src,dst=sys.argv[1],sys.argv[2]
lines=open(src,encoding='utf-8').read().splitlines()
out=[];cur_min=None;buf=[]
i=0
while i<len(lines):
    m=re.match(r'(\d+):(\d+):(\d+)\.\d+ -->',lines[i])
    if m:
        t=int(m[1])*60+int(m[2]); i+=1; txt=[]
        while i<len(lines) and lines[i].strip(): txt.append(lines[i].strip()); i+=1
        bucket=t//3*3
        if bucket!=cur_min:
            if buf: out.append(f"[{cur_min//60}:{cur_min%60:02d}] "+' '.join(buf))
            buf=[];cur_min=bucket
        buf.append(' '.join(txt))
    i+=1
if buf: out.append(f"[{cur_min//60}:{cur_min%60:02d}] "+' '.join(buf))
open(dst,'w',encoding='utf-8').write('\n'.join(out))

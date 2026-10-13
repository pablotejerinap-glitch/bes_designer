"""Carga en motors.json la columna «Type» de las tablas de motores del catálogo REDA.

Uso: python scripts/extraer_tipos_motores.py <carpeta con REDA_ESP_Catalog.pdf>
"""
import re,json,subprocess,collections
import sys
from pathlib import Path
PDF=str(Path(sys.argv[1])/'REDA_ESP_Catalog.pdf')
RUTA=Path(__file__).resolve().parents[1]/'src'/'bes'/'catalogs'/'motors.json'
M=json.loads(RUTA.read_text(encoding='utf8'))
reda=[m for m in M['motors'] if m['manufacturer']=='REDA']
pages=sorted({int(re.search(r'p\.(\d+)',m['_source']).group(1)) for m in reda})
def words(pg):
    h=subprocess.run(['pdftotext','-f',str(pg),'-l',str(pg),'-bbox',PDF,'-'],capture_output=True,text=True).stdout
    return [(float(a),float(b),e) for a,b,c,d,e in re.findall(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)</word>',h)]
res={}; problemas=[]
for pg in pages:
    w=words(pg)
    # encabezado: x de "Current," y de "Type"
    cur=[x for x,y,t in w if t=='Current,']; typ=[x for x,y,t in w if t=='Type' and y>90]
    if not cur or not typ: problemas.append((pg,'sin encabezado')); continue
    xc=cur[0]; xt=typ[-1]
    amps=sorted([(y,float(t)) for x,y,t in w if abs(x-xc)<6 and re.fullmatch(r'\d+\.\d',t)])
    rows=sorted([(y,t) for x,y,t in w if abs(x-xt)<8 and re.fullmatch(r'(S|UT|CT|LT)(-GRB)?',t)])
    # largo: palabra a la derecha del tipo en la misma fila
    lens={}
    for y,t in rows:
        c=[(x,tt) for x,yy,tt in w if abs(yy-y)<1 and x>xt+8 and re.fullmatch(r'\d+\.\d',tt)]
        lens[y]=float(min(c)[1]) if c else None
    # v50: palabra a la izquierda de la corriente en la misma fila
    labs=[]
    for y,a in amps:
        c=[(x,tt) for x,yy,tt in w if abs(yy-y)<1 and x<xc-2 and re.fullmatch(r'[\d,]+',tt)]
        c.sort(); v50=float(c[-1][1].replace(',','')) if c else None
        labs.append((y,v50,a))
    # partición contigua por centroides
    i=0; grupos=[]
    for k,(y,v,a) in enumerate(labs):
        best=None
        restantes=len(labs)-k-1
        for n in range(1,6):
            if i+n>len(rows)-restantes: break
            m=sum(r[0] for r in rows[i:i+n])/n
            if best is None or abs(m-y)<best[0]: best=(abs(m-y),n)
        if best is None: problemas.append((pg,'faltan filas')); break
        n=best[1]; g=rows[i:i+n]; i+=n
        grupos.append((v,a,[t for _,t in g],{lens[yy] for yy,_ in g},best[0]))
    if i!=len(rows): problemas.append((pg,'filas sobrantes',len(rows)-i))
    res[pg]=grupos
# asignar a motores
sin=0; amb=0
for m in reda:
    pg=int(re.search(r'p\.(\d+)',m['_source']).group(1))
    c=[g for g in res.get(pg,[]) if g[0]==m['voltage_50hz'] and abs(g[1]-m['amperage'])<0.05]
    if c: m['tipos']=sorted({t for g in c for t in g[2]}, key=['S','S-GRB','UT','UT-GRB','CT','CT-GRB','LT','LT-GRB'].index)
    else: sin+=1
print('motores con tipo:', sum('tipos' in m for m in reda), 'de', len(reda), '| páginas con problemas:', problemas)
M['_tipos_2026_09']=('Columna «Type» (S, UT, CT, LT y sus variantes -GRB) de cada tabla de motores de '
    'REDA_ESP_Catalog.pdf, leída con coordenadas (scripts/extraer_tipos_motores.py). UT = superior de tándem, '
    'CT = central, LT = inferior, S = simple. Sin «tipos»: páginas de Maximus ProMotor (traen protector integrado).')
s=json.dumps(M,indent=2,ensure_ascii=False)
RUTA.write_text(s,encoding='utf8')

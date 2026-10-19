"""Synthetic, football-realistic match event generator.

Produces event-by-event data (passes, shots, tackles, interceptions, pressure,
possession changes, fouls, cards, goals, substitutions) plus match metadata.
Everything is invented: no real match data is used.
"""
import json, math, random, sys

POS = ["GK","RB","CB","CB","LB","DM","CM","CM","RW","ST","LW"]
FIRST = ["Jack","Harry","Ollie","Reece","Callum","Tyler","Mateo","Noah","Elias","Tariq","Kofi","Felix","Rafael","Idris","Milan","Theo","Oskar","Yusuf","Marco","Leon","Nico","Sami","Jamal","Paulo","Finn","Dan","Kieran","Amari","Joe","Luca"]
LAST = ["Hartley","Pemberton","Ashworth","Whitlock","Fairbrother","Quigley","Thorne","Okafor","Moreau","Lindqvist","Duarte","Kovac","Haddad","Santos","Nakamura","Petrov","Alvarez","Diallo","Romano","Mensah","Novak","Ruiz","Costa","Aydin","Mertens","Calloway","Sutcliffe","Brennan","Ogunbanjo","Pryce"]
CLUBS = ["Harbourside City","Northgate Rovers","Redbridge Town","Westmere Athletic","Kingsway United","Thornbury Wanderers","Ironbridge Town","Calder Valley","Eastfield Rovers","Stonebridge City","Larkhill Athletic","Brightwater Town","Oakhaven Rangers","Fenwick Park","Saltmarsh United","Wexcombe City","Pennine Rovers","Hollowdene","Greyfriars Town","Redcliffe Athletic"]  # fictional clubs; any resemblance to real clubs or people is coincidental

def make_team(rng, name, strength):
    used=set(); players=[]
    for i,p in enumerate(POS):
        while True:
            n=f"{rng.choice(FIRST)} {rng.choice(LAST)}"
            if n not in used: used.add(n); break
        players.append({"id":f"{name[:3].upper()}{i+1}","name":n,"pos":p,"number":i+1,
                        "skill":round(max(0.6,min(1.4,rng.gauss(strength,0.08))),3)})
    bench=[]
    for i,p in enumerate(["CM","RW","ST","CB"]):
        while True:
            n=f"{rng.choice(FIRST)} {rng.choice(LAST)}"
            if n not in used: used.add(n); break
        bench.append({"id":f"{name[:3].upper()}{12+i}","name":n,"pos":p,"number":12+i,
                      "skill":round(max(0.6,min(1.4,rng.gauss(strength-0.03,0.08))),3)})
    return {"name":name,"strength":strength,"players":players,"bench":bench}

def xg_model(x,y):
    """Expected goals from location on 0-100 pitch (goal at x=100,y=50, pitch 105x68m)."""
    dx=(100-x)*1.05; dy=(y-50)*0.68
    d=math.hypot(dx,dy)
    ang=math.atan2(7.32*dx, dx*dx+dy*dy-(7.32/2)**2)
    ang=abs(ang)
    z=-1.0-0.17*d+1.9*ang+0.35
    return round(1/(1+math.exp(-z)),3)

def simulate(seed, home=None, away=None, hs=None, as_=None):
    _r = random.Random(seed * 7919 + 13); _c = _r.sample(CLUBS, 2); home, away = home or _c[0], away or _c[1]
    rng=random.Random(seed)
    hs=hs if hs is not None else rng.gauss(1.0,0.08)
    as_=as_ if as_ is not None else rng.gauss(1.0,0.08)
    T={"home":make_team(rng,home,hs),"away":make_team(rng,away,as_)}
    ev=[]; nid=[0]; poss_id=[0]
    score={"home":0,"away":0}
    cards={"home":0,"away":0}
    subs_done={"home":0,"away":0}
    on={s:list(T[s]["players"]) for s in T}
    t=0.0; period=1
    poss="home" if rng.random()<0.5 else "away"
    x,y=50.0,50.0
    pid=[0]; poss_id[0]=1
    def other(s): return "away" if s=="home" else "home"
    def add(typ,side,player,x=None,y=None,**kw):
        nid[0]+=1
        e={"id":nid[0],"minute":int(t//60)+(0 if period==1 else 0),"second":int(t%60),
           "period":period,"type":typ,"team":T[side]["name"],"side":side,
           "player":player["name"] if player else None,"player_id":player["id"] if player else None,
           "x":None if x is None else round(x,1),"y":None if y is None else round(y,1),
           "possession":poss_id[0],"score_home":score["home"],"score_away":score["away"]}
        e.update(kw); ev.append(e); return e
    def pick(side,weights):
        ps=on[side]; w=[weights.get(p["pos"],1)*p["skill"] for p in ps]
        return rng.choices(ps,w)[0]
    # zone weights for who is on the ball
    carry_w={"GK":0.3,"RB":1,"CB":1.2,"LB":1,"DM":1.5,"CM":1.6,"RW":1.1,"ST":0.9,"LW":1.1}
    def_w={"GK":0,"RB":1.2,"CB":1.6,"LB":1.2,"DM":1.8,"CM":1.2,"RW":0.5,"ST":0.4,"LW":0.5}
    shoot_w={"GK":0,"RB":0.3,"CB":0.3,"LB":0.3,"DM":0.6,"CM":1.2,"RW":2,"ST":3.5,"LW":2}
    total=5400+rng.randint(120,300)  # 90 minutes + stoppage (continuous play clock)
    # first half 45m + stoppage handled by period flip
    half_len=2700+rng.randint(30,120)
    add("kickoff",poss,pick(poss,carry_w),50,50)
    set_piece=None
    rng_i=random.Random(seed*131+5)
    inj_plan=sorted([(rng_i.choice([1,2]),rng_i.uniform(400,2500) if rng_i.random()<0.45 else rng_i.uniform(2850,5200),rng_i.choice(["home","away"]))
                     for _ in range(rng_i.choice([0,1,1,2]))])
    inj_plan=[(p,tt,sd) for p,tt,sd in inj_plan]
    while True:
        if period==1 and t>=half_len:
            add("half_time",poss,None); period=2; t=2700.0
            poss=other(poss); poss_id[0]+=1; x,y=50.0,50.0
            add("kickoff",poss,pick(poss,carry_w),50,50); continue
        if period==2 and t>=5400+rng.randint(150,330):
            add("full_time",poss,None); break
        # injuries (separate random stream; football feeds record the stoppage and why a substitution was made)
        while inj_plan and inj_plan[0][0]==period and t>=inj_plan[0][1]:
            _,_,isd=inj_plan.pop(0)
            cand=[p for p in on[isd] if p["pos"]!="GK"]
            if not cand: continue
            hurt=rng_i.choice(cand); off=rng_i.random()<0.5 and subs_done[isd]<3
            add("injury_stoppage",isd,hurt,rng_i.uniform(15,85),rng_i.uniform(10,90),duration_s=rng_i.choice([30,45,60,90,120,150]),outcome="substituted" if off else "continued")
            if off:
                inn=T[isd]["bench"][subs_done[isd]]
                on[isd][on[isd].index(hurt)]=inn; subs_done[isd]+=1
                add("substitution",isd,inn,replaces=hurt["name"],reason="injury")
        # substitutions
        if period==2 and t>3600:
            for s in ("home","away"):
                if subs_done[s]<3 and rng.random()<0.0012:
                    out=rng.choice([p for p in on[s] if p["pos"]!="GK"])
                    inn=T[s]["bench"][subs_done[s]]
                    on[s][on[s].index(out)]=inn; subs_done[s]+=1
                    add("substitution",s,inn,replaces=out["name"],reason="tactical")
        atk=poss; dfn=other(poss)
        # attacking x measured so that 100 = opponent goal for team in possession
        sa=T[atk]["strength"]; sd=T[dfn]["strength"]
        # pressure: deeper into the opponent half => more defenders
        pressure=min(1.0,0.25+0.5*(x/100))*(sd/sa)
        under=rng.random()<pressure*0.7
        player=pick(atk,carry_w)
        dt=rng.uniform(2.5,7.0); t+=dt
        r=rng.random()
        # shot decision
        in_zone = x>70 and 25<y<75
        p_shot = 0.0
        if x>78: p_shot=0.14+0.009*(x-78)
        elif x>66: p_shot=0.035
        if y<18 or y>82: p_shot*=0.35
        if r<p_shot and not set_piece:
            sh=pick(atk,shoot_w)
            sx=min(99.0,x+rng.uniform(0,6)); sy=min(90,max(10,y+rng.gauss(0,5)))
            xg=xg_model(sx,sy)*(0.85 if under else 1.0)*(0.9+0.1*sh["skill"])
            xg=max(0.01,min(0.9,round(xg,3)))
            roll=rng.random()
            gk=[p for p in on[dfn] if p["pos"]=="GK"][0]
            if roll<xg*sh["skill"]**0.8*0.95:
                outcome="goal"
            elif roll<xg+ (1-xg)*0.30: outcome="saved"
            elif roll<xg+ (1-xg)*0.52: outcome="blocked"
            else: outcome="off_target"
            ev_shot=add("shot",atk,sh,sx,sy,xg=xg,outcome=outcome,body_part=rng.choice(["right_foot","left_foot","right_foot","head"]) if sx>88 and rng.random()<0.25 else rng.choice(["right_foot","left_foot"]),under_pressure=bool(under))
            if outcome=="goal":
                score[atk]+=1
                ev_shot["score_home"]=score["home"]; ev_shot["score_away"]=score["away"]
                add("goal",atk,sh,sx,sy,xg=xg,score_home=score["home"],score_away=score["away"])
                t+=rng.uniform(40,70)
                poss=dfn; poss_id[0]+=1; x,y=50.0,50.0
                add("kickoff",poss,pick(poss,carry_w),50,50)
            elif outcome=="saved":
                add("save",dfn,gk,100-sx,100-sy)
                if rng.random()<0.25:
                    t+=rng.uniform(5,15); poss=atk; poss_id[0]+=1
                    add("corner",atk,pick(atk,{"RW":2,"LW":2,"CM":1}),100,0 if rng.random()<0.5 else 100)
                    x,y=92.0,50.0+rng.gauss(0,12)
                else:
                    poss=dfn; poss_id[0]+=1; x=max(5.0,100-rng.uniform(5,25)); y=100-y
                    add("possession_change",poss,gk,x,y,reason="keeper_claim")
                    x=12.0
            elif outcome=="blocked":
                poss=dfn; poss_id[0]+=1
                d=pick(dfn,def_w); add("block",dfn,d,100-sx,100-sy)
                x=max(10.0,100-sx+rng.uniform(5,25)); y=100-y
            else:
                poss=dfn; poss_id[0]+=1; x=8.0; y=50.0
                add("goal_kick",dfn,[p for p in on[dfn] if p["pos"]=="GK"][0],5,50)
                x=15.0
            continue
        # loss of possession
        p_loss=0.145+0.10*(1 if under else 0)*pressure + 0.04*(x/100)
        p_loss*= (sd/sa)**0.6 * (1.1-0.1*player["skill"])
        r2=rng.random()
        if r2<p_loss:
            d=pick(dfn,def_w)
            kind=rng.choices(["tackle","interception","incomplete_pass","duel_lost","foul"],[2.2,3.4,4.2,1.6,1.3])[0]
            if kind=="incomplete_pass":
                tx=min(99,x+rng.uniform(5,25)); ty=min(98,max(2,y+rng.gauss(0,18)))
                add("pass",atk,player,x,y,end_x=round(tx,1),end_y=round(ty,1),outcome="incomplete",under_pressure=bool(under))
                poss=dfn; poss_id[0]+=1
                add("possession_change",dfn,d,100-tx,100-ty,reason="pass_lost")
                x,y=100-tx,100-ty
            elif kind=="tackle":
                add("tackle",dfn,d,100-x,100-y,outcome="won",victim=player["name"])
                poss=dfn; poss_id[0]+=1
                add("possession_change",dfn,d,100-x,100-y,reason="tackle")
                x,y=100-x,100-y
            elif kind=="interception":
                tx=min(99,x+rng.uniform(5,20))
                add("interception",dfn,d,100-tx,100-y)
                poss=dfn; poss_id[0]+=1
                add("possession_change",dfn,d,100-tx,100-y,reason="interception")
                x,y=100-tx,100-y
            elif kind=="duel_lost":
                add("duel",dfn,d,100-x,100-y,outcome="won",duel_type=rng.choice(["ground","aerial"]))
                poss=dfn; poss_id[0]+=1
                add("possession_change",dfn,d,100-x,100-y,reason="duel")
                x,y=100-x,100-y
            else:  # foul by defender, free kick for attacker
                add("foul",dfn,d,100-x,100-y,fouled=player["name"])
                if rng.random()<0.09:
                    cards[dfn]+=1
                    add("yellow_card",dfn,d,100-x,100-y)
                t+=rng.uniform(8,20)
                add("free_kick",atk,player,x,y)
                if x>80 and rng.random()<0.5: x=min(x,88); continue
                continue
            if under and rng.random()<0.5:
                add("pressure",dfn,pick(dfn,def_w),x,y) if False else None
            continue
        # pass / carry progression
        fwd=rng.choices([1,0,-1],[0.46,0.32,0.22])[0]
        step={1:rng.uniform(4,18),0:rng.uniform(-3,3),-1:-rng.uniform(4,15)}[fwd]
        if x<30: step+=rng.uniform(0,4)
        nx=min(99.0,max(2.0,x+step)); ny=min(98,max(2,y+rng.gauss(0,16)))
        if rng.random()<0.16 and x>40:
            add("dribble",atk,player,x,y,end_x=round(nx,1),end_y=round(ny,1),outcome="success")
        else:
            add("pass",atk,player,x,y,end_x=round(nx,1),end_y=round(ny,1),outcome="complete",under_pressure=bool(under),
                progressive=bool(nx-x>=9))
        # sporadic pressure events by the defending side
        if rng.random()<0.13:
            add("pressure",dfn,pick(dfn,def_w),100-nx,100-ny,intensity=rng.choice(["low","medium","high"]))
        x,y=nx,ny
        if x>=98 and rng.random()<0.1:
            poss=dfn; poss_id[0]+=1; x=10.0; y=50.0
    meta={"match_id":f"SYN-{seed:05d}","home":T["home"]["name"],"away":T["away"]["name"],
          "final_score":{"home":score["home"],"away":score["away"]},
          "competition":"Synthetic League","synthetic":True,"seed":seed,
          "lineups":{s:{"players":T[s]["players"],"bench":T[s]["bench"]} for s in T},
          "team_strength":{"home":round(hs,3),"away":round(as_,3)}}
    return {"meta":meta,"events":ev}

if __name__=="__main__":
    seeds=int(sys.argv[1]) if len(sys.argv)>1 else 1
    for s in range(1,seeds+1):
        m=simulate(s)
        json.dump(m,open(f"data/match_{s:03d}.json","w"),ensure_ascii=False)
    print("wrote",seeds)

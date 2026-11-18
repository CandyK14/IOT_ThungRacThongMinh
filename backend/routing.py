import math
import time
from typing import Literal

from ortools.constraint_solver import pywrapcp, routing_enums_pb2
from pydantic import BaseModel, ConfigDict, Field


class RouteRequest(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    depot_lat: float=Field(default=10.77,ge=-90,le=90)
    depot_lon: float=Field(default=106.66,ge=-180,le=180)
    vehicles: int=Field(default=3,ge=1,le=20)
    capacity_l: int=Field(default=1000,ge=1,le=100000)
    threshold: float | None=Field(default=None,ge=0,le=100)
    seconds: int=Field(default=2,ge=1,le=10)
    include_predictions: bool=False
    uncertain_policy: Literal['review','conservative']='review'
    source: Literal['real','simulated','all']='all'


def distance_m(a,b):
    la,lb=math.radians(a[0]),math.radians(b[0]);dl=math.radians(b[1]-a[1])
    h=math.sin((lb-la)/2)**2+math.cos(la)*math.cos(lb)*math.sin(dl/2)**2
    return int(round(6371000*2*math.asin(math.sqrt(min(1,h)))))


def select_points(states,request,now):
    chosen=[];review=[]
    for b in states:
        if request.source!='all' and b['source']!=request.source: continue
        if not b['usable']:
            if request.uncertain_policy=='review':
                review.append({'id':b['id'],'reason':'Offline/cũ/lỗi/chưa biết mức đầy: cần kiểm tra','source':b['source']});continue
            fill=100;reason='Bảo thủ: giả định đầy, số đo chưa biết'
        else:
            fill=b['fill_pct'];reason='Mức đo hiện tại'
            p=b.get('prediction',{})
            if request.include_predictions and p.get('status')=='available' and p.get('valid_until',0)>=now and p.get('source')==b['source'] and p.get('anomaly') is not True:
                if p.get('fill_pct',0)>fill: fill=p['fill_pct'];reason='Dự đoán có nhãn, còn hiệu lực'
            threshold=request.threshold if request.threshold is not None else b.get('full_on_pct',80)
            if fill<threshold: continue
        chosen.append({'id':b['id'],'lat':b['lat'],'lon':b['lon'],'source':b['source'],'reason':reason,
                       'demand_l':max(1,math.ceil(b['capacity_l']*fill/100))})
    return chosen,review


def baseline(points,matrix,vehicles,capacity):
    todo=set(range(1,len(points)+1));routes=[]
    for v in range(vehicles):
        route=[0];load=0
        while True:
            eligible=[i for i in todo if load+points[i-1]['demand_l']<=capacity]
            if not eligible: break
            node=min(eligible,key=lambda i:(matrix[route[-1]][i],i));todo.remove(node)
            load+=points[node-1]['demand_l'];route.append(node)
        route.append(0)
        routes.append({'vehicle':v+1,'nodes':route,'load_l':load,
                       'distance_m':sum(matrix[a][b] for a,b in zip(route,route[1:]))})
    return routes,sorted(todo)


def solve(states,request,now=None):
    now=time.time() if now is None else now;started=time.perf_counter()
    points,review=select_points(states,request,now)
    if len(points)>100: raise ValueError('Demo giới hạn 100 điểm thu gom')
    depot=(request.depot_lat,request.depot_lon)
    coords=[depot]+[(p['lat'],p['lon']) for p in points]
    matrix=[[distance_m(a,b) for b in coords] for a in coords]
    base,base_dropped=baseline(points,matrix,request.vehicles,request.capacity_l)
    manager=pywrapcp.RoutingIndexManager(len(coords),request.vehicles,0)
    routing=pywrapcp.RoutingModel(manager)
    transit=routing.RegisterTransitCallback(lambda a,b:matrix[manager.IndexToNode(a)][manager.IndexToNode(b)])
    routing.SetArcCostEvaluatorOfAllVehicles(transit)
    demands=[0]+[p['demand_l'] for p in points]
    demand=routing.RegisterUnaryTransitCallback(lambda index:demands[manager.IndexToNode(index)])
    routing.AddDimensionWithVehicleCapacity(demand,0,[request.capacity_l]*request.vehicles,True,'Capacity')
    penalty=(max(map(max,matrix),default=0)+1)*(len(points)+request.vehicles+2)
    for n in range(1,len(coords)): routing.AddDisjunction([manager.NodeToIndex(n)],penalty)
    params=pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy=routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic=routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    params.time_limit.seconds=request.seconds
    solution=routing.SolveWithParameters(params)
    routes=[];dropped=[]
    if solution:
        for v in range(request.vehicles):
            index=routing.Start(v);nodes=[]
            while not routing.IsEnd(index): nodes.append(manager.IndexToNode(index));index=solution.Value(routing.NextVar(index))
            nodes.append(0)
            routes.append({'vehicle':v+1,'nodes':nodes,'load_l':sum(demands[n] for n in nodes),
                           'distance_m':sum(matrix[a][b] for a,b in zip(nodes,nodes[1:]))})
        for n in range(1,len(coords)):
            idx=manager.NodeToIndex(n)
            if solution.Value(routing.NextVar(idx))==idx:dropped.append(n)
    else: dropped=list(range(1,len(coords)))
    def format_routes(values):
        return [dict(r,stops=['depot' if n==0 else points[n-1]['id'] for n in r['nodes']],
                     coordinates=[coords[n] for n in r['nodes']]) for r in values]
    total=sum(r['distance_m'] for r in routes);base_total=sum(r['distance_m'] for r in base)
    same=set(dropped)==set(base_dropped) and solution is not None
    return {'status':'partial' if dropped else 'solved' if solution else 'no_solution',
            'solver':'OR-Tools CVRP; nghiệm tốt nhất tìm được trong giới hạn, không chứng minh tối ưu toàn cục',
            'distance_source':'Haversine, đường thẳng địa lý mô phỏng; không phải đường xe chạy',
            'capacity_assumption':'lít ước lượng = dung tích thùng × % chiều cao; giả định tiết diện đều và rác phân bố đều; không phải kg',
            'depot':depot,'points':points,'routes':format_routes(routes),'total_distance_m':total,
            'unserved':[dict(points[n-1],unserved_reason='Nhu cầu vượt sức chứa một xe' if demands[n]>request.capacity_l else 'Giới hạn tổng sức chứa/thời gian tìm kiếm') for n in dropped],
            'manual_review':review,'elapsed_seconds':round(time.perf_counter()-started,3),
            'baseline':{'method':'nearest_neighbor_capacity','routes':format_routes(base),'distance_m':base_total,
                        'unserved':[points[n-1]['id'] for n in base_dropped]},
            'comparison':{'same_served_set':same,'distance_reduction_pct':round(100*(base_total-total)/base_total,2) if same and base_total else None}}

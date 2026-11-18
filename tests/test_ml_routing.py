import copy
import json
import time
from datetime import datetime,timezone

import pytest

from backend.ml import LOOKBACK,Predictor,dataset,features,train
from backend.routing import RouteRequest,solve
from simulator.generate import generate


def test_simulator_reproducible_missing_and_faults():
    a=list(generate(3,2,42,end=1700000000));b=list(generate(3,2,42,end=1700000000))
    assert a==b
    assert any(r['message']['quality']=='fault' for r in a)
    assert any(r['anomaly_label'] for r in a)
    assert len(a)<3*(2*288+1)


def test_features_causal_and_cold_start(tmp_path):
    records=list(generate(1,.2,42,end=1700000000));messages=[r['message'] for r in records]
    assert Predictor(tmp_path/'missing').predict([],'simulated')['status']=='unavailable'
    assert Predictor(tmp_path/'missing').predict(messages,'simulated',now=1700004000)['status']=='unavailable'
    prefix=messages[:20];x=features(prefix)
    future=copy.deepcopy(messages);future[25]['fill_pct']=99
    import numpy as np
    np.testing.assert_array_equal(x,features(future[:20]))
    p=Predictor(tmp_path/'missing').predict(messages,'simulated',now=1700000000)
    assert p['status']=='available' and p['method']=='linear' and p['model_version'] is None
    messages[-1]['lid_state']='FAULT'
    assert Predictor(tmp_path/'missing').predict(messages,'simulated',now=1700000000)['status']=='unavailable'
    messages[-1]['lid_state']='CLOSED'
    messages[-1]['quality']='fault';messages[-1]['fill_pct']=None
    assert Predictor(tmp_path/'missing').predict(messages,'simulated',now=1700000000)['status']=='unavailable'


def test_train_purged_split_artifact_and_repeatability(tmp_path):
    path=tmp_path/'seed.jsonl';data=list(generate(2,6,17,end=1700000000))
    path.write_text('\n'.join(json.dumps(r) for r in data),encoding='utf-8')
    report=train(path,tmp_path/'model.joblib');again=train(path,tmp_path/'model2.joblib')
    assert report==again
    assert report['split']['train']['last_target'] < report['split']['validation']['first_feature']-LOOKBACK-300
    assert report['split']['validation']['last_target'] < report['split']['test']['first_feature']-LOOKBACK-300
    assert 'persistence' in report['test'] and 'linear' in report['test']
    predictor=Predictor(tmp_path/'model.joblib')
    h=[r['message'] for r in data if r['message']['bin_id']=='sim-001']
    p=predictor.predict(h,'simulated',now=1700000000);assert p['model_version']==report['version']
    p=predictor.predict(h,'real',now=1700000000);assert p['method']=='linear' and p['model_version'] is None


def test_anomaly_inference_failure_really_returns_baseline(tmp_path):
    from unittest.mock import Mock
    from backend.ml import baselines
    history=[r['message'] for r in generate(1,.2,42,end=1700000000)]
    predictor=Predictor(tmp_path/'missing.joblib')
    predictor.artifact={'report':{'horizon_seconds':3600,'source':'simulated',
                                 'selected_using_validation':'random_forest_depth14','version':'broken-model'},
                        'forest':Mock(),'isolation':Mock()}
    predictor.artifact['forest'].predict.return_value=[0]
    predictor.artifact['isolation'].predict.side_effect=RuntimeError('isolated inference failure')
    p=predictor.predict(history,'simulated',now=1700000000)
    expected=baselines(features(history).reshape(1,-1),3600)['linear'][0]
    assert p['method']=='linear' and p['model_version'] is None
    assert abs(p['fill_pct']-expected)<.01


def point(i,fill=90,usable=True,capacity=120):
    return {'id':f'b{i}','lat':10.77+i*.005,'lon':106.66+i*.004,'source':'simulated','usable':usable,
            'fill_pct':fill,'capacity_l':capacity,'prediction':{}}


def assert_capacity(result,capacity):
    for route in result['routes']+result['baseline']['routes']:
        assert route['load_l']<=capacity
        assert route['stops'][0]=='depot' and route['stops'][-1]=='depot'


def test_vrp_empty_single_depot():
    r=solve([],RouteRequest(seconds=1));assert r['unserved']==[] and r['total_distance_m']==0
    r=solve([point(1)],RouteRequest(vehicles=1,capacity_l=200,seconds=1))
    assert len(r['points'])==1 and not r['unserved'];assert_capacity(r,200)
    assert r['comparison']['same_served_set']


def test_vrp_multiple_vehicles_infeasible_and_stale():
    states=[point(i,100,capacity=60) for i in range(1,4)]
    r=solve(states,RouteRequest(vehicles=2,capacity_l=100,seconds=1));assert_capacity(r,100)
    assert len(r['unserved'])==1
    r=solve([point(1,100,capacity=101)],RouteRequest(vehicles=2,capacity_l=100,seconds=1))
    assert len(r['unserved'])==1 and 'vượt' in r['unserved'][0]['unserved_reason']
    r=solve([point(1,None,False)],RouteRequest(seconds=1));assert not r['points'] and len(r['manual_review'])==1
    r=solve([point(1,None,False)],RouteRequest(seconds=1,uncertain_policy='conservative'))
    assert r['points'][0]['demand_l']==120


def test_routing_prediction_expiry_source_and_negative_capacity():
    now=time.time();b=point(1,20)
    b['prediction']={'status':'available','fill_pct':95,'valid_until':now-1,'source':'simulated'}
    r=solve([b],RouteRequest(seconds=1,include_predictions=True));assert not r['points']
    b['prediction']['valid_until']=now+60
    r=solve([b],RouteRequest(seconds=1,include_predictions=True));assert len(r['points'])==1
    b['prediction']['anomaly']=True
    r=solve([b],RouteRequest(seconds=1,include_predictions=True));assert not r['points']
    with pytest.raises(ValueError):RouteRequest(capacity_l=-1)

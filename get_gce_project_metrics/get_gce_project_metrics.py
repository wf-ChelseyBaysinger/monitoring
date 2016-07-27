from gce import call_api, get_app_http
import sys
import boto3
import json
import base64
import math
from apiclient.discovery import build
import strict_rfc3339
from flask import request, abort
# import cPickle
import time
# from datetime import datetime



client = boto3.resource('dynamodb')
metrics = boto3.client('cloudwatch')
cloudmonitoring_client = build('cloudmonitoring', 'v2beta1')

def get_metric_data(project, role, metric):
    print" get_metrics",metric
    # Authorize via OAuth 2.0
    http = get_app_http()
    #last_run = get_state(project, metric)
    last_run = get_state(project, metric)
    youngest = strict_rfc3339.now_to_rfc3339_utcoffset()
    timespan = str(last_run) + 's'
    oldest_endtime = 0
    message = 'get_metric_data call_api - Project: {} Metric: {}'.format(project, metric)
    # print ("message",message)
    metric_data = call_api(http, cloudmonitoring_client, 'timeseries', 'list',
                           project=project, youngest=youngest,
                           metric=metric, timespan=timespan)
    
    # print 'timespan',timespan
    oldest_endtime = parse_metric_data(http, metric_data, project, youngest, timespan, metric, role)
    # print 'oldest endtime' , oldest_endtime
    # print "Metric data:",metric_data
    

    if oldest_endtime > 0:
        ts = oldest_endtime
        # print "ts",ts
        set_state(project, metric, ts)
        result = {'last_update': ts}
    else:
        result = {'last_update': 0}
    return json.dumps(result)
    


def set_state(project,metric,statetime):
    # print('set_state - Get Records')
    table = client.Table('gae_metrics_timestamp')
    # print "statetime", statetime
    response = table.put_item(
        Item={
            'project':project,
            'metricName': metric,
            'time': statetime
        }
    )
        # print("Adding State for project: %s metric: %s" % (project, metric))
        # p = OverseerCloudMonitoringProjectState(project_name=project, metric_name=metric, time=statetime)
        # p.put()
    print("Updating State for project: %s metric: %s" % (project, metric))
    print('set_state - Done')
    


def get_state(project, metric):
    print('get_state - Get Records')
    table = client.Table('gae_metrics_timestamp')
    last_run = None
    current_time = int(time.time())
    # print 'current time',current_time
    response = table.get_item(
        Key={
            'project':project,
            'metricName': metric
        }
    )
    if 'Item' in response:
        # print response
      # last time it was ran
        old_time = response['Item']['time']
        # print 'oldtime',old_time
        # timespan
        last_run = (current_time - old_time)
        # .total_seconds()
    
    if last_run > 3600 or last_run is None:
        last_run = 3600
    return math.trunc(last_run)






def lambda_handler(event,contex):
    http = get_app_http()
    for record in event['Records']:
        # print "record", record
        #Kinesis data is base64 encoded so decode here
        payload=base64.b64decode(record["kinesis"]["data"])
        print("Decoded payload: " + payload)
        try:
            print "try"
            data =json.loads(payload)
            print "data",data
        except:
            print "Encountered error when processing payload"
            print payload
            continue
        get_metric_data(data['project'], data['role'], data['metric'])
    return 0





def put_metrics(metric,dd_host,role,valueList):
    print "metrics",metric
    metrics = boto3.client('cloudwatch')
    # print "valuelist",valueList
    metric_data = []
    
    for value in valueList:
        data ={}
        data['MetricName'] = metric
        data['Dimensions'] = [{
            'Name':'Role',
            'Value':role
            },
            {
            'Name':'Host',
            'Value':dd_host
            }
            ]
        data['Timestamp'] = value[0]
        data['Value'] = value[1]
        metric_data.append(data)
    try:
        response = metrics.put_metric_data(
   
            Namespace='Workiva/MetricsTest',
            MetricData = metric_data
        )
        # print "response",response
    except:
        try:
            response = metrics.put_metric_data(
   
                Namespace='Workiva/MetricsTest',
                MetricData = metric_data
            )
            
        except:
            print "Could not submit metrics" , metric_data
            raise 
    # print "put_metrics response",response


def parse_metric_data(http, metric_data, project, youngest, timespan, metric, role):
    dd_tasks = list()
    oldest_endtime = 0
    if metric_data is False:
        print('No Metric Data' + str(http) + str(metric_data) +
                        str(project) + str(youngest) + str(timespan) + str(metric) + str(role))
        return oldest_endtime
    if 'timeseries' in metric_data:
        for timeseries in metric_data['timeseries']:
            # print('parse_metric_data - Parsing timeseries')
            ts_metric_name = str(timeseries['timeseriesDesc']['metric'])
            if str(metric) != ts_metric_name:
                print('Metric Does Not Match Request')
                print("metric data",metric_data)
                abort(500)
            dd_host = project
            for key, value in timeseries['timeseriesDesc']['labels'].items():
                key_name = key.split('/', 1)
                if key_name[1] == 'instance_name':
                    dd_host = str(value)
                # tags.append(key_name[1] + ':' + str(value))
            points = timeseries['points']

            int64Value_data = list()
            lowerBound_data = list()
            upperBound_data = list()
            count_data = list()
            for point in points:
                ts = int(strict_rfc3339.rfc3339_to_timestamp(point['end']))
                if ts > oldest_endtime:
                    oldest_endtime = ts
                if 'int64Value' in point:
                    value = float(point['int64Value'])
                    int64Value_data.append((ts, value))
                    if len(int64Value_data) > 19:
                        # put_metrics(metric,dd_host,role,int64Value_data)
                        # api_metric(metric, int64Value_data, host=dd_host, role=role)
                        int64Value_data = list()
                if 'doubleValue' in point:
                    value = float(point['doubleValue'])
                    int64Value_data.append((ts, value))
                    if len(int64Value_data) > 19:
                        # api_metric(metric, int64Value_data, host=dd_host, role=role)
                       # put_metrics(metric,dd_host,role,int64Value_data)
                       int64Value_data = list()
                if 'distributionValue' in point:
                    for bucket in point['distributionValue']['buckets']:
                        lowerBound = float(bucket['lowerBound'])
                        upperBound = float(bucket['upperBound'])
                        count = float(bucket['count'])
                        lowerBound_data.append((ts, lowerBound))
                        upperBound_data.append((ts, upperBound))
                        count_data.append((ts, count))
                        if len(lowerBound_data) > 19:
                            # api_metric(metric+'.min', lowerBound_data, dd_host, role)
                            # print "value lower bound" , lowerBound_data
                            put_metrics(metric+'.min',dd_host,role,lowerBound_data)
                            
                            lowerBound_data = list()
                        if len(upperBound_data) > 19:
                            # api_metric(metric+'.max', upperBound_data, dd_host, role)
                            # print "value upper bound" , upperBound_data
                            put_metrics(metric+'.max',dd_host,role,upperBound_data)
                            
                            upperBound_data = list()
                        if len(count_data) > 19:
                            # api_metric(metric+'.count', count_data, dd_host, role)
                            # print "value count data" , count_data
                            put_metrics(metric+'.count',dd_host,role,count_data)
                           
                            count_data = list()
                    dd_tasks = list()
            if len(int64Value_data) > 0:
                # api_metric(metric, int64Value_data, dd_host, role)
                put_metrics(metric,dd_host,role,int64Value_data)
               
            if len(lowerBound_data) > 0:
                # api_metric(metric+'.min', lowerBound_data, dd_host, tags)
                put_metrics(metric+'.min',dd_host,role,lowerBound_data)
               
            if len(upperBound_data) > 0:
                # api_metric(metric+'.max', upperBound_data, dd_host, tags)
                put_metrics(metric+'.max',dd_host,role,upperBound_data)
              
            if len(count_data) > 0:
                # api_metric(metric+'.count', count_data, dd_host, tags)
                put_metrics(metric+'.count',dd_host,role,count_data)

  
    dd_tasks = list()
    if 'nextPageToken' in metric_data:
        token = metric_data['nextPageToken']
        print('parse_metric_data - Found Next Page Token: ' + token)
        print('parse_metric_data - call_api')
        next_metric_data = call_api(http, cloudmonitoring_client, 'timeseries', 'list',
                                    project=project, youngest=youngest,
                                    metric=metric, timespan=timespan, pageToken=token)
        print('parse_metric_data - parse_metric_data')
        nextpage_oldest_endtime = parse_metric_data(http, next_metric_data, project, youngest, timespan, metric, role)
        if nextpage_oldest_endtime > oldest_endtime:
            oldest_endtime = nextpage_oldest_endtime
    return oldest_endtime



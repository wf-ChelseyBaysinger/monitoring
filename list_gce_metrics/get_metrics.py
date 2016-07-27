import boto3
import random
import json
from gce import call_api, get_app_http
from apiclient.discovery import build


cloudmonitoring_client = build('cloudmonitoring', 'v2beta1')
client = boto3.client('kinesis')


def lambda_handler(event, context):
    shard = random.randrange(100000000)
    http = get_app_http()
    metrics = get_metrics("amplified-vine-651",http)
    # print "metrics",metrics
    for project in metrics:
        # print "project" , project
        print "name", project['name']
        response = client.put_record(
            StreamName='gaeMetrics',
            Data = """{"project":"amplified-vine-651",
            "role":"internal",
            "metric": "%s"}"""%project['name'],
            PartitionKey=str(shard),
        )
    print response

    
def get_metrics(project,http):
    metric_list = call_api(http, cloudmonitoring_client, 'metricDescriptors', 'list', project=project)
    # print 'metrics list',metric_list
    if metric_list is not False and 'metrics' in metric_list:
        # print  "metric list, get_metrics ",metric_list['metrics']
        return metric_list['metrics']
    else:
        return False
#!/bin/bash
rm get_gce_project_metrics.zip
cd get_gce_project_metrics
zip -r ../pushGaeMetricToCloudwatch.zip *
cd ..
aws s3 cp pushGaeMetricToCloudwatch.zip s3://w-lambda-deployer-dev-us-east-1/

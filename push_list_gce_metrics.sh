#!/bin/bash
rm getGaeMetricsList.zip
cd list_gce_metrics
zip -r ../getGaeMetricsList.zip *
cd ..
aws s3 cp getGaeMetricsList.zip s3://w-lambda-deployer-dev-us-east-1/

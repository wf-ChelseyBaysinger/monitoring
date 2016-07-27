# Google Oauth
import os
import time
import sys
import httplib2
import simplejson as json
import dateutil.parser
import io
import csv
from apiclient.discovery import build
from oauth2client.service_account import ServiceAccountCredentials
from apiclient.errors import HttpError as HttpError
from oauth2client import client
from flask import session, redirect, url_for

# Setup Oauth
SCOPE = ['https://www.googleapis.com/auth/appengine.admin',
         'https://www.googleapis.com/auth/compute',
         'https://www.googleapis.com/auth/monitoring.readonly',
         'https://www.googleapis.com/auth/pubsub',
         'https://www.googleapis.com/auth/cloud-platform']
# Setup Decarator used for running API calls as the user.
CLIENT_SECRETS = os.path.join(os.path.dirname(__file__),
                              'client_secret.json')
# Helpful message to display in the browser if the CLIENT_SECRETS file is missing.
MISSING_CLIENT_SECRETS_MESSAGE = '''File client_secrets.json is missing.'''

# Setup Auth for Application

# app_http = app_credentials.authorize(httplib2.Http(memcache))

user_http = None

cloudresource_manager = build("cloudresourcemanager", "v1beta1")
copmute_service = build("compute", "v1")
storage_service = build('storage', 'v1')
pubsub_service = build('pubsub', 'v1beta2')
permissions_service = build("appengine", "v1beta2")
sink_service = build("logging", "v1beta3")

def get_app_http():
    app_credentials = ServiceAccountCredentials.from_json_keyfile_name(CLIENT_SECRETS, SCOPE)
    return app_credentials.authorize(httplib2.Http())


def get_users_http():
    global my_http
    if 'credentials' not in session:
        return redirect(url_for('oauth2callback'))
    credentials = client.OAuth2Credentials.from_json(session['credentials'])
    if credentials.access_token_expired:
        return redirect(url_for('oauth2callback'))
    return credentials.authorize(httplib2.Http())


#@cache.memoize(3600)
#def get_local_gcp_operation_data():
#    ops_data = {}
#    for record in GCPOperationsData.query():
#        name = record.project_name
#        gce_instance_count = record.gce_instance_count
#        gae_last_update = record.gae_last_update
#        ops_data[name] = {'gce_instance_count': gce_instance_count,
#                                  'gae_last_update': gae_last_update
#                                  }
#    return ops_data


#@cache.memoize(60)
def get_project(project, http=get_app_http, mytoken=None):
    if mytoken is None:
        resp = call_api(http, cloudresource_manager, 'projects', 'get', projectId=project)
    else:
        resp = call_api(http, cloudresource_manager, 'projects', 'get', projectId=project, pageToken=mytoken)
    if resp:
        resp['w_labels'] = {}
        if 'labels' in resp:
            for label in resp['labels']:
                resp['w_labels'][label['key']] = label['value']
    return resp


#@cache.memoize(120)
def get_projects(http=None, mytoken=None):
    my_projects = list()
    if mytoken is None:
        resp = call_api(http, cloudresource_manager, 'projects', 'list', pageSize=100)
        # req = developerprojects_service.projects().list(maxResults=100)
    else:
        resp = call_api(http, cloudresource_manager, 'projects', 'list', pageSize=100, pageToken=mytoken)
         # resp = call_api(http, developerprojects_service, 'projects', 'list', maxResults=100, token=mytoken)
        # req = developerprojects_service.projects().list(maxResults=100, token=mytoken)
    # resp = req.execute(http=http)
    app.logger.debug(resp)
    my_projects += resp['projects']
    if 'nextPageToken' in resp:
        newtoken = resp['nextPageToken']
        my_projects += get_projects(http, mytoken=newtoken)
    ops_data = get_local_gcp_operation_data()
    for project in my_projects:
        project['w_lables'] = {}
        if project['lifecycleState'] == 'ACTIVE':
            project['lifecycleState'] = 'Active'
        elif project['lifecycleState'] == 'DELETE_REQUESTED':
            project['lifecycleState'] = 'Pending Delete'

        if 'labels' in project:
            for key,value in project['labels'].iteritems():
                project['w_lables'][key] = value
        # Get Local Project Operational Data
        project['gce_instance_count'] = 0
        project['gae_last_update'] = 0
        if project['projectId'] in ops_data:
            project['gce_instance_count'] = ops_data[project['projectId']]['gce_instance_count']
            project['gae_last_update'] = ops_data[project['projectId']]['gae_last_update']

    return my_projects


def get_gae_modules(project, http=None):
    req = permissions_service.apps().modules().list(appId=project, maxResults=100)
    try:
        resp = req.execute(http=http)
    except HttpError, err:
        err_content = json.loads(err.content)
        print (err.content)
        return False
    else:
        my_modules = list()
        if 'modules' in resp:
            for module in resp['modules']:
                my_modules.append(module['moduleId'])
        return my_modules


def get_gae_last_updated(project, module='default', http=None):
    req = permissions_service.apps().modules().versions().list(appId=project, moduleId=module, maxResults=100)
    try:
        resp = req.execute(http=http)
    except HttpError, err:
        err_content = json.loads(err.content)
        print (err.content)

    else:
        deployedTimestamp = None
        for version in resp['versions']:
            app.logger.debug(version['deployedTimestamp'])
            thisdeployedTimestamp = dateutil.parser.parse(version['deployedTimestamp'])
            if deployedTimestamp is None or thisdeployedTimestamp > deployedTimestamp:
                deployedTimestamp = thisdeployedTimestamp
        return deployedTimestamp


def get_zones(project, http=None, mytoken=None):

    my_zones = list()
    if mytoken is None:
        resp = call_api(http, copmute_service, 'zones', 'list', maxResults=100, project=project)
        # req = developerprojects_service.projects().list(maxResults=100)
    else:
        resp = call_api(http, copmute_service, 'zones', 'list', maxResults=100, project=project, pageToken=mytoken)
    if resp is not False:
        my_zones += resp['items']
        if 'nextPageToken' in resp:
            newtoken = resp['nextPageToken']
            my_zones += get_zones(project=project, http=http, mytoken=newtoken)
    return my_zones


def get_gce_instances(project, zone, http=None, mytoken=None):
    my_instances = list()
    if mytoken is None:
        resp = call_api(http, copmute_service, 'instances', 'list', maxResults=100, project=project, zone=zone)
        # req = developerprojects_service.c
    else:
        resp = call_api(http, copmute_service, 'instances', 'list', maxResults=100, project=project, zone=zone, pageToken=mytoken)
    if resp is not False:
        if 'items' in resp:
            my_instances += resp['items']
        if 'nextPageToken' in resp:
            newtoken = resp['nextPageToken']
            my_instances += get_zones(project=project, zone=zone, mytoken=newtoken)
    return my_instances


def get_google_billing(billdate, mytoken=None):

    http = get_app_http()

    objectName = "workiva-%s.csv" % billdate.strftime('%Y-%m-%d')
    app.logger.debug("Retreiving %s" % objectName)
    if mytoken is None:
        resp = call_api(http, storage_service, 'objects', 'get_media', bucket='usage-export-data', object=objectName)
    else:
        resp = call_api(http, storage_service, 'objects', 'get_media',
                        bucket='usage-export-data', object=objectName, token=mytoken)
    if resp is not False:
        app.logger.debug("Got billing file from bucket")
        known_projects = {p.number: p.id for p in GoogleProject.query.all() if p.number > 1}
        nrows = resp.count("\n") - 1
        with io.BytesIO(resp) as f:
            reader = csv.DictReader(f)
            count = 0
            ndel = GoogleBillEntry.query.filter_by(bill_date=billdate).delete(synchronize_session='fetch')
            app.logger.debug("Deleted %d old entries before processing import." % ndel)
            for row in reader:
                count += 1
                project_id_string = None
                try:
                    project_number = int(row['Project'])
                except ValueError:
                    app.logger.info("Got '%s' when expecting project number." % row['Project'])
                    p = google_project_by_idstring(row['Project'])
                    if p is not None:
                        project_number = p.number
                        if project_number == 1:
                            known_projects[1] = p.id
                        app.logger.info("Found project by id string '%s'." % (row['Project']))
                    else:
                        app.logger.info("Also failed to find known project with id string '%s'." % row['Project'])
                        project_number = 0
                        project_id_string = row['Project']
                if project_number == 0 or project_number not in known_projects:
                    # Add new record with just project number; if number is unknown, use 1
                    new_project = GoogleProject(project_number or 1)
                    if project_id_string is not None:
                        new_project.id_string = project_id_string
                    sqldb.session.add(new_project)
                    sqldb.session.flush()
                    if new_project.number > 1:
                        known_projects[new_project.number] = new_project.id
                    project_id = new_project.id
                else:
                    project_id = known_projects[project_number]
                strs = row['Line Item'].split('/')
                service = strs[2]
                line_item = strs[3]
                value = row['Measurement1 Total Consumption']
                unit = row['Measurement1 Units']
                cost = row['Cost']
                new_entry = GoogleBillEntry(project_id,
                                            service, line_item,  value, unit, cost, billdate)
                sqldb.session.add(new_entry)
            sqldb.session.commit()
        return count
    app.logger.debug("Error retreiving billing file from bucket")
    return False


#@cache.memoize(3600)
def google_project_by_idstring(id_string):
    return GoogleProject.query.filter_by(id_string=id_string).first()


def call_api(http, client, class_name, function, **kwargs):
    # if int(qps) > 0:
    #     qps_sleep = 1/int(qps)
    #     time.sleep(qps_sleep)
    retry = 0
    failed = False
    # print(client.__dict__[class_name]())
    obj = client.__dict__[class_name]()
    try:
        func = getattr(obj, function)
    except AttributeError:
        print ('function not found "%s" (%s)' % (function, obj))
    else:
        while True:
            try:
                print (str(client) + str(class_name) + str(function) + str(kwargs))
                result = func(**kwargs)
                print http
                resp = result.execute(http=http)
            except HttpError, error:
                try:
                    content = json.loads(error.content)
                except:
                    print (error)
                else:
                    try:
                        reason = content.get('error').get('errors')[0].get('reason')
                        app.logger.info(str(client) + str(class_name) + str(function) + str(kwargs))
                        if reason == 'userRateLimitExceeded':
                            if retry < 1:
                                app.logger.info('Rate Limited - Sleeping 10')
                                time.sleep(10)
                                retry += 1
                                continue
                            else:
                                print ('RateLimit - Retry Limit Exceded')
                                failed = True
                                break
                        else:
                            print ('Error - {}'.format(reason))
                            print (error.content)
                            failed = True
                            break
                    except:
                        print ("Unkown GAE API: " + str(content))
                        if retry < 1:
                            print ('Unkown GAE API - Retry')
                            retry += 1
                            continue
                        else:
                            print ('Unkown GAE API - Retry Limit Exceded')
                            failed = True
                            break
            except:
                exc_type, exc_value = sys.exc_info()[:2]
                print ('Handling %s exception with message "%s"' % (exc_type.__name__, exc_value))
                if retry < 1:
                    print ('Unkown Error - Sleeping 10')
                    time.sleep(10)
                    retry += 1
                    continue
                else:
                    print ('Unkown Error - Retry Limit Exceded')
                    failed = True
                    break
            else:
                return resp
        if failed:
            print ('Call API Failed.')
            return False


def subscribe_pubsub(project, topic):
    body = {
         "name": topic,
    }
    create_Topic =pubsub_service.projects().topics().create(
                        name="projects/"+project+"/topics/"+topic, body=body)
    body = {
        "destination": "pubsub.googleapis.com/projects/"+project+"/topics/"+topic,
    }
    create_Sink = sink_service.projects().logs().sinks().create(
                    projectsId=project,logsId=create_Topic, body=body)

    push_endpoint = "https://cloudops.workiva.net/pubsub_client/"+topic+"/"+project
    # Create a POST body for the Pub/Sub request
    body = {
        # The name of the topic from which this subscription receives messages
        'topic': 'projects/' + project + '/topics/' + topic,
        # Only needed if you are using push delivery
        'pushConfig': {
            'pushEndpoint': push_endpoint
        }
    }
    subscription = pubsub_service.projects().subscriptions().create(
                    name='projects/amplified-vine-651/subscriptions/'+topic+'_'+project,
                    body=body).execute(http=get_app_http)


    print 'Created: %s' % subscription.get('name')


def unsubscribe_pubsub(project, topic):
    subscription = pubsup_service.projects().subscriptions().delete(
        subscription='projects/amplified-vine-651/subscriptions/' + topic + '_' + project).execute(http=get_app_http)

    print 'Created: %s' % subscription.get('name')


def enable_overseer_monitor(project, service):
    ProjectConfig = OverseerProjectConfig.query(OverseerProjectConfig.project_name == project)
    record = ProjectConfig.get()
    if record is None:
        return {'error': True, "msg": "Project Not Found"}
    else:
        if service == 'logpubsub':
            subscribe_pubsub(project, 'cloud_logs')
            setattr(record, service + "_enabled", True)
            # record.endpoint_enabled = True
            record.put()
            return {'error': False, "msg": service + " for project enabled"}
        else:
            setattr(record, service + "_enabled", True)
            # record.endpoint_enabled = True
            record.put()
            return {'error': False, "msg": service + " for project enabled"}



def disable_overseer_monitor(project, service):
    ProjectConfig = OverseerProjectConfig.query(OverseerProjectConfig.project_name == project)
    record = ProjectConfig.get()
    if record is None:

        return {'error': True, "msg": "Project Not Found"}
    else:
        if service == 'logpubsub':
            unsubscribe_pubsub(project, 'cloud_logs')
            setattr(record, service + "_enabled", False)
            # record.endpoint_enabled = True
            record.put()
            return {'error': False, "msg": service + " for project disabled"}
        else:
            setattr(record, service + "_enabled", False)
            # record.endpoint_enabled = False
            record.put()
            return {'error': False, "msg": service + " for project disabled"}


def sync_overseer_appspots():
    projects = get_projects(get_app_http())
    app.logger.debug(projects)
    app.logger.info("Syncing Overseer Appspots")
    for project in projects:
        if "role" in project['w_lables']:
            app.logger.debug('Found %s with role %s' % (project['projectId'], project['w_lables']['role']))
            # See if we are in ndb already
            ProjectConfig = OverseerProjectConfig.query(OverseerProjectConfig.project_name == project['projectId'])
            record = ProjectConfig.get()
            if record is None:
                app.logger.info("Adding Project %s with role %s" % (project['projectId'], project['w_lables']['role']))
                p = OverseerProjectConfig(role_name=project['w_lables']['role'], project_name=project['projectId'])
                p.put()
            else:
                app.logger.info("Updating Project %s with role %s" % (project['projectId'], project['w_lables']['role']))
                record.role_name = project['w_lables']['role']
                record.put()


def save_overseer_task_queue_list(project, task_queues):
    ProjectConfig = OverseerProjectConfig.query(OverseerProjectConfig.project_name == project)
    record = ProjectConfig.get()
    if record is None:

        return {'error': True, "msg": "Project Not Found"}

    else:
        record.task_queues = task_queues
        record.put()

        return {'error': False, "msg": "Project Task Queue Saved"}


# @cache.cached(timeout=300)
def get_users_projects():
    http = get_users_http()
    return get_projects(http)


# @cache.cached(timeout=300)
def get_all_projects():
    return get_projects(get_app_http())

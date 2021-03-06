#!/usr/bin/env python3
import os
import sys
import argparse
import requests
import datetime
import json
import time


from fiotools import __version__
from fiotools import configuration
from fiotools.utils import rfile


def cmd_parser():
    parser = argparse.ArgumentParser(
        description='Interact with the fio web service',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--version",
        action='store_true',
        default=False,
        help="Show fioloadgen version"
    )

    subparsers = parser.add_subparsers(help="sub-commands")

    parser_status = subparsers.add_parser('status', help="show the status of the web service")
    parser_status.set_defaults(func=command_status)

    parser_profile = subparsers.add_parser(
        'profile',
        help='view and manage the fio profiles')
    parser_profile.set_defaults(func=command_profile)
    parser_profile.add_argument(
        '--show',
        type=str,
        metavar='<profile name>',
        help="show content of an fio profile",
    )
    parser_profile.add_argument(
        '--ls',
        action='store_true',
        help="list available fio profiles",
    )
    parser_profile.add_argument(
        '--refresh',
        action='store_true',
        help="apply fio profiles in data/fio/jobs to the local database and the remote fiomgr pod",
    )

    parser_run = subparsers.add_parser(
        'run',
        help="run a given fio profile")
    parser_run.set_defaults(func=command_run)
    parser_run.add_argument(
        '--profile',
        required=True,
        metavar='<profile name>',
        help="fio profile for the fio workers to execute against",
    )
    parser_run.add_argument(
        '--workers',
        default=9999,
        required=False,
        metavar='<# of workers>',
        help="number of workers to use for the profile",
    )
    parser_run.add_argument(
        '--provider',
        required=False,
        default='aws',
        type=str,
        choices=['aws', 'vmware', 'baremetal', 'azure', 'gcp'],
        help="Infrastructure provider where the test is running",
    )
    parser_run.add_argument(
        '--platform',
        required=False,
        default='openshift',
        type=str,
        choices=['openshift', 'kubernetes', 'ssh'],
        help="platform running the workload",
    )
    parser_run.add_argument(
        '--title',
        required=True,
        type=str,
        metavar='<text>',
        help="descriptive title of the run (used in reports and charts)",
    )
    parser_run.add_argument(
        '--wait',
        action='store_true',
        help="wait for the run to complete - NOT IMPLEMENTED YET",
    )

    parser_job = subparsers.add_parser(
        'job',
        help="show fio job information")
    parser_job.set_defaults(func=command_job)
    parser_job.add_argument(
        '--ls',
        action="store_true",
        help="list all jobs",
    )
    parser_job.add_argument(
        '--queued',
        action="store_true",
        help="additional parameter for --ls to limit results to only queued jobs",
    )
    parser_job.add_argument(
        '--show',
        type=str,
        metavar='<Job ID>',
        help="show content of an job",
    )
    parser_job.add_argument(
        '--delete',
        type=str,
        metavar='<Job ID>',
        help="delete a queued job",
    )
    parser_job.add_argument(
        '--raw',
        action='store_true',
        help="show raw json from a completed job",
    )

    parser_db_dump = subparsers.add_parser(
        'db-dump',
        help="manage the jobs table in the fioservice database")
    parser_db_dump.set_defaults(func=command_db_dump)
    # example:  db-dump --table jobs --row id=0ca72318-c4ed-4a17-b81a-262c44a52fdc
    parser_db_dump.add_argument(
        '--table',
        choices=['jobs', 'profiles'],
        default='jobs',
        type=str,
        help="dump a table (jobs or profiles from the database (default is jobs)",
    )
    parser_db_dump.add_argument(
        '--out',
        type=str,
        required=False,
        help="filename for the database dump output",
    )

    parser_db_export = subparsers.add_parser(
        'db-export',
        help="export a database row to a script file (for import)")
    parser_db_export.set_defaults(func=command_db_export)
    parser_db_export.add_argument(
        '--table',
        choices=['jobs', 'profiles'],
        default='jobs',
        type=str,
        help="table name to export a row from",
    )
    parser_db_export.add_argument(
        '--row',
        default='',
        required=True,
        type=str,
        help="query string (key=value) that identifies a specific row in the table",
    )
    parser_db_export.add_argument(
        '--out',
        type=str,
        help="filename for the exported row output",
    )

    parser_db_import = subparsers.add_parser(
        'db-import',
        help="import a database row export file")
    parser_db_import.set_defaults(func=command_db_import)
    parser_db_import.add_argument(
        '--table',
        default='jobs',
        choices=['jobs', 'profiles'],
        type=str,
        help="table to restore the export file to (either jobs or profiles)",
    )
    parser_db_import.add_argument(
        '--file',
        default='',
        required=True,
        type=str,
        help="backup file to import to the database",
    )
    parser_db_delete = subparsers.add_parser(
        'db-delete',
        help="delete a row from a table")
    parser_db_delete.set_defaults(func=command_db_delete)
    parser_db_delete.add_argument(
        '--table',
        choices=['jobs', 'profiles'],
        default='jobs',
        type=str,
        help="table where the row will be deleted from (default is jobs)",
    )
    parser_db_delete.add_argument(
        '--row',
        default='',
        required=True,
        type=str,
        help="query string (key=value) that identifies a specific row in the table",
    )
    return parser


def _build_qry_string(qs):
    try:
        k, v = args.row.split('=')
    except ValueError:
        # trigger if >1 '=' sign or no '=' sign at all
        return ''
    else:
        return '?{}'.format(qs)


def _extract_API_error(response):
    js = json.loads(response._content.decode())
    return "Error: {}".format(js['message'])    


def command_db_delete():
    qstring = _build_qry_string(args.row)
    if not qstring:
        print("row must specify a single key=value string i.e. --row id=mykey")
        sys.exit(1)

    r = requests.delete("{}/db/{}{}".format(url, args.table, qstring))
    if r.status_code == 200:
        print("database table row from '{}' deleted".format(args.table))
    else:
        print("database delete API request failed: {}".format(r.status_code))
        print(_extract_API_error(r))


def command_db_export():
    outfile = ''

    qstring = _build_qry_string(args.row)
    if not qstring:
        print("row must specify a single key=value string i.e. --row id=mykey")
        sys.exit(1)

    if args.out:
        outfile = args.out
    else:
        outfile = os.path.join(os.path.expanduser('~'), "fioservice-db-{}-row.sql".format(args.table))

    r = requests.get("{}/db/{}{}".format(url, args.table, qstring))
    if r.status_code == 200:
        with open(outfile, 'wb') as f:
            f.write(r.content)
        print("database table row from '{}' written to {}".format(args.table, outfile))
    else:
        print("database dump API request failed: {}".format(r.status_code))
        print(_extract_API_error(r))


def command_db_import():
    # file must contain a single insert into "<table>" clause
    if not os.path.exists(args.file):
        print("file not found")
        sys.exit(1)

    sql_script = rfile(args.file)
    if sql_script.count('INSERT INTO "{}"'.format(args.table)) != 1:
        print("file invalid format - must contain a single INSERT command")
        sys.exit(1)

    headers = {'Content-type': 'application/json'}
    r = requests.post(
        "{}/db/{}".format(url, args.table),
        json={
            "sql_script": sql_script,
        },
        headers=headers
    )
    if r.status_code == 200:
        print("data import successful")
    else:
        print("database import failed: {}".format(r.status_code))
        print(_extract_API_error(r))


def command_db_dump():
    outfile = ''

    if args.out:
        outfile = args.out
    else:
        outfile = os.path.join(os.path.expanduser('~'), "fioservice-db-{}.sql".format(args.table))

    r = requests.get("{}/db/{}".format(url, args.table))
    if r.status_code == 200:
        with open(outfile, 'wb') as f:
            f.write(r.content)
        print("database dump of table '{}' written to {}".format(args.table, outfile))
    else:
        print("database dump API request failed: {}".format(r.status_code))


def command_status():
    try:
        r = requests.get("{}/status".format(url))
    except (requests.exceptions.ConnectionError, ConnectionRefusedError):
        print("Please start the fioservice, before using the cli")
        sys.exit(1)

    if r.status_code == 200:
        js = r.json()['data']

        job_running = 'Yes' if js['task_active'] else 'No'
        debug = 'Yes' if js['debug_mode'] else 'No'
        print("Target      : {}".format(js['target']))
        print("Debug Mode  : {}".format(debug))
        print("Job running : {}".format(job_running))
        print("Jobs queued : {}".format(js['tasks_queued']))
        print("Uptime      : {}".format(str(datetime.timedelta(seconds=int(js['run_time'])))))
    else:
        print("Failed to retrieve web service status [{}]".format(r.status_code))


def command_profile():
    if args.ls:
        r = requests.get("{}/profile".format(url))
        data = r.json()['data']
        for p in data:
            print("- {}".format(p['name']))
    elif args.show:
        if args.show not in profiles:
            print("The server doesn't have a profile called '{}'. Available profiles are: {}".format(args.show, ', '.join(profiles)))
            sys.exit(1)

        r = requests.get("{}/profile/{}".format(url, args.show))
        data = r.json()['data']
        print(data)
    elif args.refresh:
        # refresh the profiles from the local filesystem
        r = requests.get("{}/profile?refresh=true".format(url))
        if r.status_code == 200:
            print("Profiles refreshed from the filesystem versions")
            summary = r.json()['summary']
            for k in summary:
                print(" - {:<11s}: {:>2}".format(k, len(summary[k])))
        else:
            print("Profile refresh failed: {}".format(r.status_code))


def show_summary(api_response):
    keys_to_show = ['id', 'title', 'started', 'profile', 'workers', 'status']  # NOQA
    data = json.loads(api_response.json()['data'])
    for k in keys_to_show:
        if k == 'started':
            if data['started']:
                print("Run Date : {}".format(datetime.datetime.fromtimestamp(data[k]).strftime('%Y-%m-%d %H:%M:%S')))  # NOQA
            else:
                print("Run Date : pending")
        else:
            print("{:<9}: {}".format(k.title(), data[k]))
    if data.get('summary', None):
        print("Summary  :")
        js = json.loads(data['summary'])
        for k in js.keys():
            print("  {}: {}".format(k.title(), js[k]))
    else:
        print("Summary  : Unavailable (missing)")


def job_wait(job_uuid):

    try:
        while True:
            r = requests.get("{}/job/{}".format(url, job_uuid))
            if r.status_code != 200:
                break
            js = json.loads(r.json()['data'])
            if js['status'] in ['complete', 'failed']:
                break
            sys.stdout.write(".")
            sys.stdout.flush()
            time.sleep(2)
    except KeyboardInterrupt:
        print("\nWait aborted")
        sys.exit(1)
    print("\n")
    return r


def command_run():
    print("Run fio workload profile {}".format(args.profile))
    headers = {'Content-type': 'application/json'}
    r = requests.post('{}/job/{}'.format(url, args.profile),
                      json={
                          "workers": args.workers,
                          "title": args.title,
                          "provider": args.provider,
                          "platform": args.platform
                      },
                      headers=headers)

    if r.status_code == 202:
        response = r.json()['data']
        print("- Request queued with uuid = {}".format(response['uuid']))
        if args.wait:
            print("Running.", end="")
            completion = job_wait(response['uuid'])
            if completion.status_code == 200:
                show_summary(completion)
            else:
                print("- Request failed with status code {}".format(completion.status_code))
    else:
        print("- Request failed")


def command_job():
    if args.ls:

        # show all jobs in the db
        field_list = ['id', 'status', 'title', 'ended']
        r = requests.get("{}/job?fields={}".format(url, ','.join(field_list)))
        data = r.json()['data']
        sdata = sorted(data, key=lambda i: i['ended'] if i['ended'] else 9999999999, reverse=True)
        print("{:<37}  {:<11}  {:^19}  {}".format('Job ID', 'Status', "End Time", "Job Title"))
        row_count = 0
        for p in sdata:
            if args.queued and p['status'] != 'queued':
                continue

            if p['ended']:
                end_time = datetime.datetime.fromtimestamp(p['ended']).strftime("%Y-%m-%d %H:%M:%S")
            else:
                end_time = 'N/A'

            print("{:<37}  {:<11}  {:^19}  {}".format(p['id'], p['status'], end_time, p['title']))
            row_count += 1
        print("Jobs: {:>3}".format(row_count))

    elif args.show:
        # show a specific job record
        r = requests.get("{}/job/{}".format(url, args.show))
        if r.status_code == 200:
            show_summary(r)
            if args.raw:
                jstr = json.loads(r.json()['data'])['raw_json']
                js = json.loads(jstr)
                try:
                    print(json.dumps(js, indent=2))
                except BrokenPipeError:
                    pass
        elif r.status_code == 404:
            print("Job with id '{}', does not exist in the database".format(args.show))
        else:
            print("Unknown status returned : {}".format(r.status_code))
    elif args.delete:
        # delete a queued job
        r = requests.delete("{}/job/{}".format(url, args.delete))
        if r.status_code == 200:
            print("Queued job '{}' has been marked for deletion".format(args.delete))
        else:
            handle_error(r)
    elif args.raw:
        print("Syntax error: the --raw parameter can only be used with --show <job id>")


def handle_error(response):
    js = response.json()
    print("{} [{}]".format(js.get('message', "Server didn't return an error description!"), response.status_code))


if __name__ == '__main__':

    profiles = []
    parser = cmd_parser()
    args = parser.parse_args()

    if args.version:
        print("fioloadgen version : {}".format(__version__))

    elif 'func' in args:
        configuration.init()

        api_address = os.environ.get(
            'FIO_API_ADDRESS',
            '{}:{}'.format(
                configuration.settings.ip_address,
                configuration.settings.port
            )
        )
        url = 'http://{}/api'.format(api_address)  # used by all functions
        if args.func.__name__ == 'command_status':
            args.func()
        else:
            try:
                r = requests.get('{}/profile'.format(url))
            except (requests.exceptions.ConnectionError, ConnectionRefusedError):
                print("Please start the fioservice, before using the cli")
                sys.exit(1)

            profiles = [p['name'] for p in r.json()['data']]

            args.func()
    else:
        print("skipped")

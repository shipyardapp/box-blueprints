import os
import re
import json
import argparse
import glob
import shipyard_utils as shipyard

from boxsdk import Client, JWTAuth
from boxsdk.exception import *

import logging
logging.getLogger('boxsdk').setLevel(logging.CRITICAL)


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-file-name-match-type',
                        dest='source_file_name_match_type',
                        default='exact_match',
                        choices={
                            'exact_match',
                            'regex_match'},
                        required=False)
    parser.add_argument(
        '--source-file-name',
        dest='source_file_name',
        required=True)
    parser.add_argument(
        '--source-folder-name',
        dest='source_folder_name',
        default='',
        required=False)
    parser.add_argument(
        '--destination-folder-name',
        dest='destination_folder_name',
        default='',
        required=False)
    parser.add_argument(
        '--destination-file-name',
        dest='destination_file_name',
        default=None,
        required=False)
    parser.add_argument(
        '--service-account',
        dest='service_account',
        default=None,
        required=True)
    return parser.parse_args()


def set_environment_variables(args):
    """
    Set Box Service Account Credentials as environment variables if they're provided via keyword
    arguments rather than seeded as environment variables. This will override
    system defaults.
    """
    if args.service_account:
        os.environ['BOX_APPLICATION_CREDENTIALS'] = args.service_account
    return


def upload_box_file(
        client,
        source_full_path,
        destination_full_path,
        folder_id):
    """
    Uploads a single file to Box.
    """
    destination_file_name = destination_full_path.rsplit('/', 1)[-1]
    try:
        new_file = client.folder(folder_id).upload(
            source_full_path, file_name=destination_file_name)
    except Exception as e:
        if hasattr(e, 'code') and e.code == 'item_name_in_use':
            file_id = e.context_info['conflicts']['id']
            updated_file = client.file(
                file_id).update_contents(source_full_path)
        else:
            print(f'Failed to upload file {source_full_path}')
            raise (e)

    print(f'{source_full_path} successfully uploaded to '
          f'{destination_full_path}')


def get_client(service_account):
    """
    Attempts to create the Box Client with the associated with the credentials.
    """
    try:
        if os.path.isfile(service_account):
            auth = JWTAuth.from_settings_file(service_account)
        else:
            service_dict = json.loads(service_account)
            auth = JWTAuth.from_settings_dictionary(service_dict)

        client = Client(auth)
        client.user().get()
        return client
    except BoxOAuthException as e:
        print(f'Error accessing Box account with pervice account '
              f'developer_token={developer_token}; client_id={client_id}; '
              f'client_secret={client_secret}')
        raise (e)


def get_single_folder_id(client, folder, folder_filter=None):
    """
    Returns a folder id for the provided folder name and folder_folder id.
    """
    # Wrap in quotes for exact match
    folder_id = None
    search_folder = '"' + folder + '"'
    print(f'Looking up {folder}')
    folder_matches = client.search().query(
        query=search_folder,
        result_type='folder',
        ancestor_folder_ids=folder_filter)

    for folder_match in folder_matches:
        if folder_match.name == folder:
            folder_id = folder_match.id
    print(f'Folder ID for {folder} is {folder_id}')
    return folder_id


def get_folder_id(client, destination_folder_name):
    """
    Returns the folder obj for the Box client if it exists.
    """
    folder = None
    # Strip destination_folder_name for last subdirectory
    # Wrap search folder in quotes for exact match

    folder_parts = destination_folder_name.strip('/').rsplit('/')
    print(folder_parts)

    for index, folder in enumerate(folder_parts):
        if index == 0:
            folder_id = get_single_folder_id(client, folder)
            print(folder_id)
        else:
            folder_id = get_single_folder_id(
                client, folder, folder_filter=folder_id)

    if folder_id:
        return folder_id
    else:
        # sys.exit(ec.EXIT_CODE_FOLDER_DOES_NOT_EXIST)
        return create_folders(client, destination_folder_name)


def create_folder(client, folder_name, subfolder='0'):
    """
    Creates the folder for the Box client.
    """
    # Check if we're creating in the root folder
    subfolder_id = '0'
    if subfolder != '0':
        subfolder_id = subfolder.id

    try:
        subfolder = client.folder(subfolder_id).create_subfolder(folder_name)
    except Exception as e:
        print(f'Folder {folder_name} already exists')
        folder_id = e.context_info['conflicts'][0]['id']
        subfolder = client.folder(folder_id=folder_id).get()

    return subfolder


def create_folders(client, destination_folder_name):
    """
    Creates the folder destination_folder_name for the Box client.
    """
    try:
        folders = destination_folder_name.split('/')
        if len(folders) > 0:
            subfolder = create_folder(client, folders[0])

            for folder in folders[1:]:
                subfolder = create_folder(client, folder, subfolder)

            return subfolder
    except (BoxOAuthException, BoxAPIException) as e:
        print(f'Could not create folder {destination_folder_name}')
        raise (e)


def main():
    args = get_args()
    set_environment_variables(args)
    service_account = os.environ.get('BOX_APPLICATION_CREDENTIALS')
    source_file_name = args.source_file_name
    source_folder_name = args.source_folder_name
    source_full_path = shipyard.files.combine_folder_and_file_name(
        folder_name=f'{os.getcwd()}/{source_folder_name}',
        file_name=source_file_name)
    destination_file_name = args.destination_file_name
    destination_folder_name = shipyard.files.clean_folder_name(
        args.destination_folder_name)
    source_file_name_match_type = args.source_file_name_match_type

    client = get_client(service_account=service_account)
    folder = '0'
    # code.interact(local=locals())
    if destination_folder_name:
        folder_id = get_folder_id(
            client, destination_folder_name=destination_folder_name)

    if source_file_name_match_type == 'regex_match':
        file_names = shipyard.files.find_all_local_file_names(
            source_folder_name)
        matching_file_names = shipyard.files.find_all_file_matches(
            file_names, re.compile(source_file_name))
        print(f'{len(matching_file_names)} files found. Preparing to upload...')

        for index, file_name in enumerate(matching_file_names):
            destination_full_path = shipyard.files.determine_destination_full_path(
                destination_folder_name=destination_folder_name,
                destination_file_name=args.destination_file_name,
                source_full_path=file_name, file_number=index + 1)

            print(f'Uploading file {index+1} of {len(matching_file_names)}')
            upload_box_file(
                source_full_path=file_name,
                destination_full_path=destination_full_path,
                client=client, folder_id=folder)

    else:
        destination_full_path = shipyard.files.determine_destination_full_path(
            destination_folder_name=destination_folder_name,
            destination_file_name=args.destination_file_name,
            source_full_path=source_full_path)

        upload_box_file(source_full_path=source_full_path,
                        destination_full_path=destination_full_path,
                        client=client, folder_id=folder_id)


if __name__ == '__main__':
    main()

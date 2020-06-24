import numpy as np
import requests
import datetime
import time

from . import endpoints
from . import infoservice
from .endpoints import chunkedgraph_api_versions, chunkedgraph_endpoints_common, default_global_server_address
from .base import _api_endpoints, _api_versions, ClientBase
from .auth import AuthClient
import requests

SERVER_KEY = 'cg_server_address'

def package_bounds(bounds):
    bounds_str = []
    for b in bounds:
        bounds_str.append("-".join(str(b2) for b2 in b))
    bounds_str = "_".join(bounds_str)
    return bounds_str


def ChunkedGraphClient(server_address=None,
                       table_name=None,
                       auth_client=None,
                       api_version='latest',
                       timestamp=None
                      ):
    if server_address is None:
        server_address = default_global_server_address

    if auth_client is None:
        auth_client = AuthClient()

    auth_header = auth_client.request_header
    
    endpoints, api_version = _api_endpoints(api_version, SERVER_KEY, server_address,
                                            chunkedgraph_endpoints_common, chunkedgraph_api_versions, auth_header)

    ChunkedClient = client_mapping[api_version]
    return ChunkedClient(server_address,
                      auth_header,
                      api_version,
                      endpoints,
                      SERVER_KEY,
                      timestamp=timestamp,
                      table_name=table_name)

class ChunkedGraphClientLegacy(ClientBase):
    """Client to interface with the PyChunkedGraph service

    Parameters
    ----------
    server_address : str or None, optional
        URL where the PyChunkedGraph service is running. If None, defaults to www.dynamicannotationframework.com
    table_name : str or None, optional
        Name of the chunkedgraph table associated with the dataset. If the datastack_name is specified and table name is not, this can be looked up automatically. By default, None.
    auth_client : auth.AuthClient or None, optional
        Instance of an AuthClient with token to handle authorization. If None, does not specify a token.
    timestamp : datetime.datetime or None, optional
        Default UTC timestamp to use for chunkedgraph queries. 
    """
    def __init__(self,
                 server_address,
                 auth_header,
                 api_version,
                 endpoints,
                 server_key=SERVER_KEY,
                 timestamp=None,
                 table_name=None):
        super(ChunkedGraphClientLegacy, self).__init__(server_address,
                                                      auth_header,
                                                      api_version,
                                                      endpoints,
                                                      server_key)

        self._default_url_mapping['table_id']=table_name
        self._default_timestamp=timestamp
        self._table_name = table_name
        self._default_timestamp=timestamp

    @property
    def default_url_mapping(self):
        return self._default_url_mapping.copy()

    @property
    def table_name(self):
        return self._table_name

    def get_root_id(self, supervoxel_id, timestamp=None):
        """Get the root id for a specified supervoxel

        Parameters
        ----------
        supervoxel_id : np.uint64
            Supervoxel id value
        timestamp : datetime.datetime, optional
            UTC datetime to specify the state of the chunkedgraph at which to query, by default None. If None, uses the current time.

        Returns
        -------
        np.uint64
            Root ID containing the supervoxel.
        """
        if timestamp is None:
            if self._default_timestamp is not None:
                timestamp = self._default_timestamp
            else:
                timestamp = datetime.datetime.utcnow()

        endpoint_mapping = self.default_url_mapping
        endpoint_mapping['supervoxel_id']=supervoxel_id
        url = self._endpoints['handle_root'].format_map(endpoint_mapping)

        if timestamp is None:
            timestamp=self._default_timestamp
        if timestamp is not None:
            query_d ={
                'timestamp': time.mktime(timestamp.timetuple())
            }
        else:
            query_d = None
        response = self.session.get(url, params=query_d)

        response.raise_for_status()
        return np.int64(response.json()['root_id'])

    def get_merge_log(self, root_id):
        """Returns the merge log for a given object

        Parameters
        ----------
        root_id : np.uint64
            Root id of an object to get merge information.

        Returns
        -------
        list
            List of merge events in the history of the object.
        """
        endpoint_mapping = self.default_url_mapping
        endpoint_mapping['root_id'] = root_id
        url = self._endpoints['merge_log'].format_map(endpoint_mapping)
        response = self.session.post(url, json=[root_id])

        response.raise_for_status()
        return response.json()

    def get_change_log(self, root_id):
        """Get the change log (splits and merges) for an object

        Parameters
        ----------
        root_id : np.uint64
            Object root id to look up

        Returns
        -------
        list
            List of split and merge events in the object history
        """
        endpoint_mapping = self.default_url_mapping
        endpoint_mapping['root_id'] = root_id
        url = self._endpoints['change_log'].format_map(endpoint_mapping)
        response = self.session.post(url, json=[root_id])

        response.raise_for_status()
        return response.json()

    def get_leaves(self, root_id, bounds=None):
        """Get all supervoxels for a root_id

        Parameters
        ----------
        root_id : np.uint64
            Root id to query
        bounds: np.array or None, optional
            If specified, returns supervoxels within a 3x2 numpy array of bounds [[minx,maxx],[miny,maxy],[minz,maxz]]
            If None, finds all supervoxels.

        Returns
        -------
        list
            List of supervoxel ids
        """
        endpoint_mapping = self.default_url_mapping
        endpoint_mapping['root_id'] = root_id
        url = self._endpoints['leaves_from_root'].format_map(endpoint_mapping)
        query_d = {}
        if bounds is not None:
            query_d['bounds'] = package_bounds(bounds)

        response = self.session.get(url, params=query_d)

        response.raise_for_status()
        return np.int64(response.json()['leaf_ids'], dtype=np.int64)

    def get_children(self, node_id):
        """Get the children of a node in the hierarchy

        Parameters
        ----------
        node_id : np.uint64
            Node id to query

        Returns
        -------
        list
            List of np.uint64 ids of child nodes.
        """
        endpoint_mapping = self.default_url_mapping
        endpoint_mapping['node_id'] = node_id
        url = self._endpoints['handle_children'].format_map(endpoint_mapping)

        response = self.session.post(url)

        response.raise_for_status()
        return np.frombuffer(response.content, dtype=np.uint64)

    def get_contact_sites(self, root_id, bounds, calc_partners=False):
        """Get contacts for a root id

        Parameters
        ----------
        root_id : np.uint64
            Object root id
        bounds: np.array
            Bounds within a 3x2 numpy array of bounds [[minx,maxx],[miny,maxy],[minz,maxz]] for which to find contacts. Running this query without bounds is too slow.
        calc_partners : bool, optional
            If True, get partner root ids. By default, False.
        Returns
        -------
        dict
            Dict relating ids to contacts
        """
        endpoint_mapping = self.default_url_mapping
        endpoint_mapping['root_id'] = root_id
        url = self._endpoints['contact_sites'].format_map(endpoint_mapping)
        query_d = {}
        if bounds is not None:
            query_d['bounds'] = package_bounds(bounds)
        query_d['partners'] = calc_partners
        response = self.session.post(url, json=[root_id], params=query_d)
        contact_d = response.json()
        return {int(k): v for k, v in contact_d.items()}

    @property
    def cloudvolume_path(self):
        return self._endpoints['cloudvolume_path'].format_map(self.default_url_mapping)

client_mapping = {0: ChunkedGraphClientLegacy,
                  1: ChunkedGraphClientLegacy,
                  'latest': ChunkedGraphClientLegacy}
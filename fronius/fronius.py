
import requests
import json
from requests.auth import HTTPDigestAuth
import hashlib
import logging

logger = logging.getLogger('__main__')
logger.info(f'[Fronius] loading module ')

def hash_utf8(x):
    if isinstance(x, str):
        x = x.encode("utf-8")
    return hashlib.md5(x).hexdigest()

class FroniusWR(object):
    def __init__(self, address, user, password) -> None:
        self.address = address
        self.capacity = -1
        self.min_soc = 8 # in percent
        self.max_soc = 100
        self.max_charge_rate=2500 #Watt
        self.max_grid_power=5000 #Watt
        self.nonce = 0
        self.user = user
        self.password = password
        self.previous_config=self.get_battery_config()

    def get_SOC(self):
        path='/solar_api/v1/GetPowerFlowRealtimeData.fcgi'
        response = self.send_request(path)
        result = json.loads(response.text)
        soc = result['Body']['Data']['Inverters']['1']['SOC']
        return soc
    def get_free_capacity(self):
        current_soc=self.get_SOC()
        capa=self.get_capacity()
        free_capa=(self.max_soc-current_soc)/100*capa
        return free_capa
    
    def get_stored_energy(self):
        current_soc=self.get_SOC()
        capa=self.get_capacity()
        energy=(current_soc-self.min_soc)/100*capa
        return energy
    
    def get_usable_capacity(self):
        usable_capa=(self.max_soc-self.min_soc)/100*self.get_capacity()
        return usable_capa
        
    def get_battery_config(self):
        path='/config/batteries'
        response = self.send_request(path, auth=True)
        result = json.loads(response.text)
        return result
    def restore_battery_config(self):
        settings_to_restore=[
            'BAT_M0_SOC_MAX',
            'BAT_M0_SOC_MIN',
            'BAT_M0_SOC_MODE',
            'HYB_BM_CHARGEFROMAC',
            'HYB_EM_MODE',
            'HYB_EM_POWER',
            'HYB_EVU_CHARGEFROMGRID'
        ]
        settings={}
        for key in settings_to_restore:
            if key in self.previous_config.keys():
                settings[key]=self.previous_config[key]
            else:
                RuntimeError(f"Unable to restore settings. Parameter {key} is missing")
        path='/config/batteries'
        payload=json.dumps(settings)
        logger.info(f'[Fronius] Restoring previous battery configuration: {payload} ')
        response = self.send_request(path,method='POST',payload=payload, auth=True)
        response_dict=json.loads(response.text)
        expected_write_successes=settings_to_restore
        for expected_write_success in expected_write_successes:
            if not expected_write_success in response_dict['writeSuccess']:
                raise RuntimeError(f'failed to set {expected_write_success}')
        return response
    
    def set_min_soc(self, soc):
        path='/config/batteries'
        payload=f'{{"BAT_M0_SOC_MIN": {soc:d}, "BAT_M0_SOC_MODE": "manual"}}'
        response = self.send_request(path,method='POST',payload=payload, auth=True)
        response_dict=json.loads(response.text)
        expected_write_successes=['BAT_M0_SOC_MIN','BAT_M0_SOC_MODE']
        for expected_write_success in expected_write_successes:
            if not expected_write_success in response_dict['writeSuccess']:
                raise RuntimeError(f'failed to set {expected_write_success}')
        return response
    
    def set_max_soc(self, soc):
        path='/config/batteries'
        payload=f'{{"BAT_M0_SOC_MAX": {soc:d}, "BAT_M0_SOC_MODE": "manual"}}'
        response = self.send_request(path,method='POST',payload=payload, auth=True)
        response_dict=json.loads(response.text)
        expected_write_successes=['BAT_M0_SOC_MAX','BAT_M0_SOC_MODE']
        for expected_write_success in expected_write_successes:
            if not expected_write_success in response_dict['writeSuccess']:
                raise RuntimeError(f'failed to set {expected_write_success}')
        return response
    
    def set_allow_grid_charging(self, value:bool):
        if value:
            payload='{"HYB_EVU_CHARGEFROMGRID": true}'
        else:
            payload='{"HYB_EVU_CHARGEFROMGRID": false}'
        path='/config/batteries'
        response = self.send_request(path,method='POST',payload=payload, auth=True)
        response_dict=json.loads(response.text)
        expected_write_successes=['HYB_EVU_CHARGEFROMGRID']
        for expected_write_success in expected_write_successes:
            if not expected_write_success in response_dict['writeSuccess']:
                raise RuntimeError(f'failed to set {expected_write_success}')
        return response
    
    def set_em_power(self,power:int):
        """set power at grid-connection point negative values for Feed-In"""
        path='/config/batteries'
        payload=f'{{"HYB_EM_POWER": {power:d}, "HYB_EM_MODE": 1}}' #HYB_EM_MODE 1=manual 0=automatic
        response = self.send_request(path,method='POST',payload=payload, auth=True)
        response_dict=json.loads(response.text)
        expected_write_successes=['HYB_EM_POWER','HYB_EM_MODE']
        for expected_write_success in expected_write_successes:
            if not expected_write_success in response_dict['writeSuccess']:
                raise RuntimeError(f'failed to set {expected_write_success}')
        return response
    
    def set_wr_parameters(self, minsoc, maxsoc,allow_grid_charging,grid_power):
        """set power at grid-connection point negative values for Feed-In"""
        path='/config/batteries'
        if not type(allow_grid_charging) == bool:
            raise RuntimeError(f'Expected type: bool actual type: {type(allow_grid_charging)}')
        
        grid_power=int(grid_power)
        minsoc=int(minsoc)
        maxsoc=int(maxsoc)
        
        if not 0<=grid_power<=self.max_charge_rate:
            raise RuntimeError(f'gridpower out of allowed limits {grid_power}')
        
        if minsoc>maxsoc:
            raise RuntimeError(f'Min SOC needs to be higher than Max SOC')
        
        if minsoc<self.min_soc:
            raise RuntimeError(f'Min SOC not allowed below {self.min_soc}')
        
        if maxsoc>self.max_soc:
            raise RuntimeError(f'Max SOC not allowed above {self.max_soc}')
                    
        parameters={'HYB_EVU_CHARGEFROMGRID':allow_grid_charging,
                    'HYB_EM_POWER':grid_power,
                    'HYB_EM_MODE':1,
                    'BAT_M0_SOC_MIN':minsoc,
                    'BAT_M0_SOC_MAX':maxsoc,
                    'BAT_M0_SOC_MODE':'manual'                    
                    }
        
        payload=json.dumps(parameters)
        logger.info(f'[Fronius] Setting battery parameters: {payload} ')
        
        response = self.send_request(path,method='POST',payload=payload, auth=True)
        response_dict=json.loads(response.text)
        for expected_write_success in parameters.keys():
            if not expected_write_success in response_dict['writeSuccess']:
                raise RuntimeError(f'failed to set {expected_write_success}')
        return response
        
    def get_capacity(self):
        if self.capacity >= 0:
            return self.capacity
        response = self.send_request('/solar_api/v1/GetStorageRealtimeData.cgi')
        result = json.loads(response.text)
        capacity = result['Body']['Data']['0']['Controller']['DesignedCapacity']
        self.capacity = capacity
        return capacity

    def send_request(self,  path, method='GET',payload="", params=None, headers={}, auth=False):
        for i in range(3):
            url = 'http://' + self.address+ path
            fullpath = path
            if params:
                fullpath += '?' + \
                    "&".join(
                        [f'{k+"="+str(params[k])}' for k in params.keys()])
            if auth:
                headers['Authorization'] = self.get_auth_header(
                    method=method, path=fullpath)

            response = requests.request(method=method, url=url, params=params, headers=headers,data=payload)
            if response.status_code == 200:
                return response
            elif 400 <= response.status_code < 500:
                self.nonce = self.get_nonce(response)
                response = self.login()
                if (response.status_code==200):
                    logger.info('[Fronius] Login successful')
                else:
                    logger.info('[Fronius] Login failed')
            else:
                raise RuntimeError(
                    f"Server {self.address} returned {response.status_code}")
    
    def login(self):
        params = {"user": self.user}
        path='/commands/Login'
        return self.send_request(path, auth=True)
    
    def logout(self):
        params = {"user": self.user}
        path='/commands/Logout'
        response= self.send_request(path, auth=True)
        if response.status_code==200:
            logger.info('[Fronius] Logout successful')
        else:
            logger.info('[Fronius] Logout failed')
        return response

    def get_nonce(self, response):
        auth_string = response.headers['X-WWW-Authenticate']
        auth_list = auth_string.replace(" ", "").replace('"', '').split(',')
        auth_dict = {}
        for item in auth_list:
            key, value = item.split("=")
            auth_dict[key] = value
        return auth_dict['nonce']

    def get_auth_header(self, method, path):
        nonce = self.nonce
        realm = 'Webinterface area'
        ncvalue = "00000001"
        cnonce = "NaN"
        user=self.user
        password=self.password
        if len(self.user)<4:
            raise RuntimeError("User needed for Authorization")
        if len(self.password)<4:
            raise RuntimeError("Password needed for Authorization")
            
        A1 = f"{user}:{realm}:{password}"
        A2 = f"{method}:{path}"
        HA1 = hash_utf8(A1)
        HA2 = hash_utf8(A2)
        noncebit = f"{nonce}:{ncvalue}:{cnonce}:auth:{HA2}"
        respdig = hash_utf8(f"{HA1}:{noncebit}")
        auth_header = f'Digest username="{user}", realm="{realm}", nonce="{nonce}", uri="{path}", algorithm="MD5", qop=auth, nc={ncvalue}, cnonce="{cnonce}", response="{respdig}"'
        return auth_header
    def __del__(self):
        self.restore_battery_config()
        self.logout()

""" Factory for logic classes. """
import logging

from .logic_interface import LogicInterface, CalculationInput, CalculationParameters, CalculationOutput, InverterControlSettings

class Logic:
    """ Factory for logic classes. """
    @staticmethod
    def create_logic(config: dict):
        """ Select and configure a logic class based on the given configuration """
        request_type = config.get('type', 'default').lower()
        if request_type == 'default':
            from .default_logic import DefaultLogic
            logic = DefaultLogic()
        else:
            raise RuntimeError(f'[Logic] Unknown logic type {config["type"]}')
        
        return logic
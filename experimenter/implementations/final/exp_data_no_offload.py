'''
TODO:
TODO:
Pick standards for:
    1. row selectivity.
    2. batch size.
    3. cluster size, Spark and Ceph.
    4. dataset size.

Current stuff:
    1. 10% query
    2. <need to find out optimum again>
    3. Regular 8,8
    4. 512GB
'''
from datetime import datetime

from rados_deploy import Designation

from experimenter.internal.experiment.execution.execution_interface import ExecutionInterface
import experimenter.internal.experiment.execution.functionstore.data_general as data_general
import experimenter.internal.experiment.execution.functionstore.distribution_general as distribution_general
import experimenter.internal.experiment.execution.functionstore.experiment_general as experiment_general
import experimenter.internal.experiment.execution.functionstore.spark as spark
import experimenter.internal.experiment.execution.functionstore.rados_ceph as rados_ceph

from experimenter.internal.experiment.interface import ExperimentInterface
from experimenter.internal.experiment.config import ExperimentConfigurationBuilder, ExperimentConfiguration, NodeConfiguration, CephConfiguration

import utils.fs as fs
import utils.location as loc
from utils.printer import *

def get_experiment():
    '''Pass your defined experiment class in this function so we can find it when loading.'''
    return CephExperiment()

        
def get_node_configuration():
    return NodeConfiguration(9, CephConfiguration(
        [[Designation.OSD, Designation.MON],
        [Designation.OSD, Designation.MON],
        [Designation.OSD, Designation.MON],
        [Designation.OSD, Designation.MGR],
        [Designation.OSD, Designation.MGR],
        [Designation.OSD, Designation.MDS],
        [Designation.OSD, Designation.MDS],
        [Designation.OSD, Designation.MDS]]))


# Performs experiment definition 1: We read using Arrow, using RADOS, without pushing filters.
class CephExperiment(ExperimentInterface):
    '''This interface provides hooks, which get triggered on specific moments in deployment execution.
    It is your job to implement the functions here.'''

    def __init__(self):
        super(CephExperiment, self).__init__()


    def get_executions(self):
        ''''Get experiment ExecutionInterfaces.
        Returns:
            `iterable(internal.experiment.ExecutionInterfaces)`, containing all different setups we want to experiment with.'''
        data_query = 'SELECT * FROM table WHERE total_amount > 27' #10% row selectivity, 100% column selectivity
        row_selectivities = [1, 10, 25, 50, 75, 90, 100]
        stripe = 128 # One file should have stripe size of 64MB
        multipliers = [(64, 2), (64, 4), (64, 8), (64, 16), (64, 32), (64, 64)] #Total data size: 16, 32, 64, 128, 256, 512GB
        timestamp = datetime.now().isoformat()

        configs = []
        for (copy_multiplier, link_multiplier) in multipliers:
            result_dirname = 'cp{}_ln{}'.format(copy_multiplier, link_multiplier)
            configbuilder = ExperimentConfigurationBuilder()
            configbuilder.set('batchsize', 1024)
            configbuilder.set('mode', '--arrow-only')
            configbuilder.set('runs', 21)
            configbuilder.set('spark_driver_memory', '60G')
            configbuilder.set('spark_executor_memory', '60G')
            configbuilder.set('node_config', get_node_configuration())
            configbuilder.set('stripe', stripe)
            configbuilder.set('copy_multiplier', copy_multiplier)
            configbuilder.set('link_multiplier', link_multiplier)
            configbuilder.set('remote_result_dir', fs.join('~', 'results', 'exp_data', result_dirname, str(timestamp)))
            configbuilder.set('result_dir', fs.join(loc.result_dir(), 'exp_data', result_dirname, str(timestamp)))
            configbuilder.set('data_path', fs.join(loc.data_generation_dir(), 'jayjeet_128mb.pq'))
            configbuilder.set('data_query', '"{}"'.format(data_query))
            configbuilder.set('spark_conf_options', lambda conf: ExperimentConfiguration.base_spark_conf_options(conf)+[
                'spark.arrowspark.pushdown.filters=false'
            ])
            config = configbuilder.build()
            configs.append(config)

        for idx, config in enumerate(configs):
            executionInterface = ExecutionInterface(config)
            executionInterface.register('distribute_func', distribution_general.distribute_default)
            experiment_general.register_default_experiment_function(executionInterface, idx, len(configs))
            experiment_general.register_default_result_fetch_function(executionInterface, idx, len(configs))
            rados_ceph.register_rados_ceph_deploy_data(executionInterface, idx, len(configs))
            spark.register_spark_functions(executionInterface, idx, len(configs))
            rados_ceph.register_rados_ceph_functions(executionInterface, idx, len(configs))
            yield executionInterface
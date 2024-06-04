"""
Test RPJ type Negative test_failover.

Copyright (c) 2017 Nutanix Inc. All rights reserved.

Author: sekhar.yadavali@nutanix.com
"""
# pylint: disable = no-member

from framework.lib.test.nos_test import NOSTest
from framework.lib.nulog import STEP, INFO
from framework.components.acropolis import Acropolis
from framework.components.uhura import Uhura
from framework.hypervisors.hypervisor_types import HypervisorType
from framework.lib.parallel_executor import ParallelExecutor
from workflows.metro.dr_lib import assert_true
from workflows.draas.draas_workflows import DraasWorkflow
from workflows.draas import draas_library

class DraasNegativeTestFailover(NOSTest):
  """This class defines some basic DRaaS workflows to be tested.
  """

  def setup(self):
    """Basic setup for each test.

    Returns:
      None.
    """

    self.pe_clusters = self.get_resources_by_type(self.NOS_CLUSTER)
    self.pc_clusters = self.get_resources_by_type(self.PRISM_CENTRAL)

    pc_pe_map = draas_library.get_pc_pe_map(self.pe_clusters, self.pc_clusters)
    (self.source_pc, self.source_pe_list, self.remote_pc, self.remote_pe_list) \
      = draas_library.get_source_remote_map(self.pc_clusters, pc_pe_map)

    self.draas_wo = DraasWorkflow(source_clusters=self.source_pe_list,
                                  interface=self.interface_type,
                                  source_pc=self.source_pc,
                                  remote_clusters=self.remote_pe_list,
                                  remote_pc=self.remote_pc)
    self.draas_wo.do_setup(create_uvm=False, create_rp=False)
    self.use_default_ipam = self.test_args.get('use_default_ipam', True)

  def teardown(self):
    """Basic teardown for each tests.

    Returns:
      None.
    """
    draas_library.draas_teardown_helper([self.draas_wo],
                                        test_result_status=self.result[
                                          "result"], log_dir=self.log_dir)

  def test_tfo_vm_register_failure_when_uhura_down(self):
    """
    Raises:
      NuTestError in case recovery succeeds when uhura is brought down and
        trigger RP.

    Metadata:
      Summary: This is negative test which bring down uhura on remote PE,
        and trigger RP with action_type=TEST_FAILOVER.
      Priority: $P2
      Components: [$CEREBRO]
      Services: [$AOS_TAR]
      Tags: [$AOS_DRAAS_TAR]
      Requirements: [FEAT-3429, ENG-105800, ENG-121603]
      Steps:
        - Create Test Subnets on both source and destination.
        - Create a Category.
        - Creating required UVMs with categories..
        - Process PR.
        - Create a RP with above category.
        - Trigger RP with action_type=TEST_FAILOVER, and in parallel,
          bring down uhura on remote PE.
        - ExpectedResults
          - 1. Creation of test subnets should succeed.
          - 2. Category creation should succeed.
          - 3. VM creation should succeed.
          - 4. PR process should succeed.
          - 5. RP creation should succeed.
          - 6. RPJ should fail as VM could not be created on remote
            as uhura is down on remote PE.

    """
    STEP("Create Test Subnets on both source and destination")
    self.draas_wo.create_test_subnet()

    STEP("Creating categories.")
    self.categories_list = self.test_args["categories"]
    self.draas_wo.create_categories(categories_list=self.categories_list)

    STEP("Creating required UVMs with categories.")
    self.draas_wo.create_uvms_with_category(self.categories_list,
                                            use_default_ipam=\
                                              self.use_default_ipam)

    STEP("Editing Protection rule to protect UVMs in category.")
    self.draas_wo.edit_protection_rule(categories=\
                       self.test_args["protection_rule_categories"])

    STEP("Triggering Protection rule process api.")
    self.draas_wo.process_protection_rule(validate_snaps=True,\
                                          categories_list=self.test_args\
                                          ["protection_rule_categories"])

    STEP("Creating Recovery plan to use categories.")
    rp = self.draas_wo.\
      create_recovery_plan_custom(recovery_plan_stages=self.
                                  test_args["recovery_plan_stages"])

    # Get service to make down
    service_map = {HypervisorType.ESX : Uhura,
                   HypervisorType.AHV : Acropolis}
    vm_register_service = service_map[\
      self.remote_pe_list[0].hypervisors[0].type]

    STEP("Trigger RP with action_type=TEST_FAILOVER and "
         "bring down uhura on remote PE.")
    service_to_down = vm_register_service(self.remote_pe_list[0])
    executor = ParallelExecutor()
    executor.add_task(self.draas_wo.start_recovery,\
      kwargs={'action': "TEST_FAILOVER",\
              'recovery_plan': rp})
    executor.add_task(target=service_to_down.stop, kwargs={})
    results = executor.run()

    expected_msg = "Timed out waiting for the task with uuid"
    pass_msg = "RPJ is failed as %s is down on remote PE as "\
               "expected" % vm_register_service.NAME
    fail_msg = "RPJ didn't fail or failed with unexpected error"
    error_msg = results[0].get("exception")
    INFO(error_msg)
    assert_true(expected_msg in str(error_msg), fail_msg, pass_msg)

    expected_message = "None"
    pass_msg = "%s is down on remote PE as expected" % vm_register_service.NAME
    fail_msg = "%s is up on remote PE which is unexpected"\
               % vm_register_service.NAME
    msg = results[1].get("exception")
    assert_true(expected_message == str(msg), fail_msg, pass_msg)

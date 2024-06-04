"""
Test RPJ type test_failover from Xi to OnPrem.

Copyright (c) 2018 Nutanix Inc. All rights reserved.

Author: vijayku.bellubb@nutanix.com

"""
# pylint: disable = no-member

from workflows.draas.draas_workflows import DraasWorkflow
from workflows.draas import draas_library
from framework.lib.test.nos_test import NOSTest
from framework.lib.nulog import STEP

class DraasTestFailoverXi(NOSTest):
  """This class defines test case for RPJ type rpj_type_test_failover_xi"""

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

    self.draas_wo = DraasWorkflow(source_clusters=self.source_pe_list, \
                                 interface=self.interface_type, \
                                 source_pc=self.source_pc, \
                                 remote_clusters=self.remote_pe_list, \
                                 remote_pc=self.remote_pc)

    self.draas_wo.do_setup(create_uvm=False, create_rp=False, create_pr=False)
    self.snap_ids = []


  def teardown(self):
    """Basic teardown for each test.

    Returns:
      None.
    """
    draas_library.draas_teardown_helper([self.draas_wo, self.draas_wo_remote],
                                        test_result_status=self.result[
                                          "result"], log_dir=self.log_dir)

  def test_verify_test_failover_xi_onprem(self, failover_type="TEST_FAILOVER"):
    """
    Args:
      failover_type(str): Type of failover, TEST_FAILOVER/FAILOVER
        Defaults to TEST_FAILOVER

    Metadata:
      Summary: This test performs test failover from Xi to OnPrem
      Priority: $P0
      Components: [$CEREBRO]
      Services: [$AOS_TAR]
      Tags: [$AOS_DRAAS_TAR]
      Requirements: [FEAT-3429, ENG-105800]
      Steps:
        - Create DRaasWorkflow object for remote site and do a setup for it.
        - Create test-subnet on both Xi and OnPrem.
        - Create Categories.
        - Create VMs under the category.
        - Edit PR and add the category to the PR.
        - Trigger PR process api.
        - Create recovery plan to add all the VMs that are protected.
        - Validate the recovery plan on destination.
        - Perform RPJ of type TEST_FAILOVER on the recovery plan.
        - Verify the vlan details & category of brought up VMs on OnPrem.
        - Expected Results
          - 1. Category creation should work.
          - 2. VMs creation with categories should work.
          - 3. Editing PR should work to add categories to PR.
          - 4. Vms will get protected and replicated.
          - 5. snapshot should also be replicated to remote site.
          - 6. Recovery plan creation should work and should get created with
               test network.
          - 7. Recovery plan validation should work.
          - 8. New VMs should come up on remote PC after TEST_FAILOVER.
          - 9. Verify the vlans of vms on test network, vlan of vms should
               match vlans specified in test subnet of recovery plan and
               should come up with a special category "RPTestFailover" on
               OnPrem.

    """

    STEP("Workflow for Remote: B.")
    self.draas_wo_remote = DraasWorkflow(source_clusters=self.remote_pe_list,
                                         interface=self.interface_type,
                                         source_pc=self.remote_pc,
                                         remote_clusters=self.source_pe_list,
                                         remote_pc=self.source_pc,
                                         cleanup_existing_entities=False)

    STEP("Setup Remote: B.")
    self.draas_wo_remote.do_setup(create_uvm=False, create_rp=False,
                                  bind_az=True, create_pr=True)

    if failover_type == "TEST_FAILOVER":
      STEP('Create Test Subnets on both source and destination')
      self.draas_wo_remote.create_test_subnet(test_subnet_index=0)
    self.validate_network = self.test_args["validate_network"]

    STEP("Creating categories.")
    self.categories_list = self.test_args["categories"]
    self.draas_wo_remote.create_categories(categories_list=self.categories_list)

    STEP("Creating required UVMs with categories.")
    self.draas_wo_remote.create_uvms_with_category(self.categories_list,
                                                   use_default_ipam=False)

    STEP("Editing Protection rule to protect UVMs in category.")
    self.draas_wo_remote.edit_protection_rule(
      categories=self.test_args["protection_rule_categories"])

    STEP("Triggering Protection rule process api.")
    self.draas_wo_remote.process_protection_rule(validate_snaps=True,\
                                                 categories_list=self.test_args\
                                                 ["protection_rule_categories"])

    STEP("Creating Recovery plan to use categories.")
    rp = self.draas_wo_remote.create_recovery_plan_custom(
      recovery_plan_stages=self.test_args["recovery_plan_stages"])

    STEP("Validate RP.")
    self.draas_wo_remote.start_recovery(action="VALIDATE", recovery_plan=rp)

    STEP("Starting Recovery type {0}.".format(failover_type))
    self.draas_wo_remote.start_recovery(action=failover_type, recovery_plan=rp,
                                        validate_network=self.validate_network,
                                        recovery_plan_stages=self.test_args[
                                          "recovery_plan_stages"])

  def test_verify_failover_xi_onprem(self):
    """
    Metadata:
      Summary: This test performs unplanned failover from Xi to OnPrem
      Priority: $P0
      Components: [$CEREBRO]
      Services: [$AOS_TAR]
      Tags: [$AOS_DRAAS_TAR]
      Requirements: [FEAT-3429]
      Steps:
        - Create DRaasWorkflow object for remote site and do a setup for it.
        - Create Categories.
        - Create VMs under the category.
        - Edit PR and add the category to the PR.
        - Trigger PR process api.
        - Create recovery plan to add all the VMs that are protected.
        - Validate the recovery plan on destination.
        - Perform RPJ of type FAILOVER on the recovery plan.
        - Verify the category details of brought up VMs on OnPrem.
        - Expected Results
          - 1. Category creation should work.
          - 2. VMs creation with categories should work.
          - 3. Editing PR should work to add categories to PR.
          - 4. Vms will get protected and replicated.
          - 5. snapshot should also be replicated to remote site.
          - 6. Recovery plan creation should work and should get created with
               test network.
          - 7. Recovery plan validation should work.
          - 8. New VMs should come up on remote PC after FAILOVER.

    """
    self.test_verify_test_failover_xi_onprem(failover_type="FAILOVER")

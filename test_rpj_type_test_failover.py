"""
Test cases for RPJ type TEST_FAILOVER

Copyright (c) 2017 Nutanix Inc. All rights reserved.

Author: kartik.saraswat@nutanix.com
"""
# pylint: disable = no-member

from framework.lib.test.nos_test import NOSTest
from framework.lib.nulog import STEP, INFO

from workflows.draas.draas_workflows import DraasWorkflow
from workflows.draas import draas_library
from workflows.metro.dr_lib import assert_true

class DraasTestFailover(NOSTest):
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
    self.snap_ids = []
    self.dummy_vm = self.test_args.get('dummy_vm', False)

  def teardown(self):
    """Basic teardown for each tests.

    Returns:
      None.
    """
    draas_library.draas_teardown_helper([self.draas_wo],
                                        test_result_status=self.result[
                                          "result"], log_dir=self.log_dir)

  def test_rpj_test_failover_vm_special_category_no_pr(self):
    """
    Metadata:
      Summary: This test performs VM RPJ type rpj_type_test_failover, verifies
        replicated VMs have no PR and have a special category.
      Priority: $P0
      Components: [$CEREBRO]
      Services: [$AOS_TAR]
      Requirements: [FEAT-3429, ENG-105800]
      Steps:
        - Creating 2 categories.
        - Creating 2 UVMs in each of the categories created in
          previous step.
        - Edit PR that protects the categories mentioned in step 1.
        - Trigger PR process api for the PR created in previous step.
        - Create recovery plan with above UVMs.
        - Start TEST_FAILOVER recovery and validate entity recovery on
          remote.
        - Validate recovered vms have no PR.
        - Validate recovered vms have the special category.
        - Delete VMs with special category via batch request.
        - ExpectedResults
          - 1. Category Creation should work.
          - 2. VM Creation should work.
          - 3. VMs should be auto-protected after triggering PR process api.
          - 4. Recovery Plan Creation should work.
          - 5. VMs should come up on remote.
          - 6. Recovered VMs have no PR.
          - 7. Recovered VMs have special category.
          - 8. VMs with special category are deleted.
      Tags: [$DEPRECATED, $AOS_DRAAS_TAR]

    """

    STEP('Create Test Subnets on both source and destination')
    self.draas_wo.create_test_subnet(test_subnet_index=0)

    STEP("Creating categories.")
    self.categories_list = self.test_args["categories"]
    self.draas_wo.create_categories(categories_list=self.categories_list)

    STEP("Creating required UVMs with categories")
    self.draas_wo.create_uvms_with_category(self.categories_list,
                                            dummy_vm=self.dummy_vm,
                                            use_default_ipam=False)
    STEP("Editing Protection rule to protect UVMs in category.")
    self.draas_wo.edit_protection_rule(
      categories=self.test_args["protection_rule_categories"])

    STEP("Triggering PR process api and validating snapshots replication")
    self.draas_wo.process_protection_rule(
      categories_list=self.test_args["protection_rule_categories"])

    STEP("Create recovery plan categories created above.")
    rp = self.draas_wo.create_recovery_plan_custom(
      recovery_plan_stages=self.test_args["recovery_plan_stages"])

    STEP("Start TEST_FAILOVER RPJ and validate recovered VMs are not protected")
    self.draas_wo.start_recovery(action='TEST_FAILOVER', recovery_plan=rp,
                                 recovery_plan_stages=\
                                  self.test_args['recovery_plan_stages'])

    STEP("Delete VMs Created with Special categories")
    self.draas_wo.clean_test_failover_vms()

  def test_tfo_ipam_network_exhausted(self):
    """
    Metadata:
      Summary: This test performs TFO to check VMs comes up without NICs
               when ipam network is exhausted.
      Priority: $P1
      Components: [$CEREBRO]
      Services: [$AOS_TAR]
      Tags: [$AOS_DRAAS_TAR]
      Requirements: [FEAT-3429, ENG-156525]
      Steps:
      - 1. Create category cat1:val1 and cat2:val2
      - 2. Create test subnet vlan2000 that can hold 5 IPs only.
      - 3. Create 5 VMs with cat1:val1 and 5 with cat2:val2.
      - 4. Create a PR to protect the VMs.
      - 5. Create RP1 with category cat1:val1 and RP2 with cat2:val2
           and network mapping should map to test network vlan2000.
      - 6. Trigger TFO on RP1.
      - 7. Trigger TFO on RP2
      - ExpectedResults
        - 1. Category creation should succeed.
        - 2. Test subnet creation should succeed.
        - 3. VM creation should succeed.
        - 4. PR protect should succeed.
        - 5. RP creation should succeed.
        - 6. TFO on RP1 should succeed.
        - 7. VMs from TFO on RP2 should come up without NIC.

    """

    STEP("Creating Categories")
    self.categories_list = self.test_args["categories"]
    self.draas_wo.create_categories(categories_list=self.categories_list)

    STEP("Creating test subnet")
    subnet_details = {
      self.source_pc.svm_ips[0] : {self.source_pe_list[0].svm_ips[0]:\
                                 self.test_args["test_subnet_details"]},
      self.remote_pc.svm_ips[0] : {self.remote_pe_list[0].svm_ips[0]:\
                                 self.test_args["test_subnet_details"]}}

    self.draas_wo.create_test_subnet(test_subnet_details=subnet_details,\
                                     use_default_ipam=False)

    STEP("Create UVMs with categories on source")
    self.draas_wo.create_uvms_with_category(self.categories_list)

    INFO("Editing Protection rule to protect UVMs in category.")
    things_to_edit = {}
    things_to_edit["categories"] = self.test_args["protection_rule_categories"]
    self.draas_wo.edit_protection_rule(**things_to_edit)

    STEP("Triggering Protection rule process api.")
    self.draas_wo.process_protection_rule(validate_snaps=True,\
                                          categories_list=self.test_args\
					  ["protection_rule_categories"])

    STEP("Create Recovery Plan:RP1")
    rp1 = self.draas_wo.create_recovery_plan_custom(\
          recovery_plan_stages=self.test_args["recovery_plan_stages_1"],\
          remote_subnet_name="vlan2000",\
          map_all_networks=False)

    STEP("Create Recovery Plasn:RP2")
    rp2 = self.draas_wo.create_recovery_plan_custom(\
          recovery_plan_stages=self.test_args["recovery_plan_stages_2"],\
          remote_subnet_name="vlan2000",\
          map_all_networks=False)

    STEP("Start Recovery for RP1")
    self.draas_wo.start_recovery(action="TEST_FAILOVER",\
                                   validate_recovery_order=True,\
                                   return_recovered_vm_list=True,\
                                   validate_network=False,\
                                   recovery_plan=rp1)

    STEP("Start Recovery for RP2")
    recovered_vms = self.draas_wo.start_recovery(action="TEST_FAILOVER",\
                                   validate_recovery_order=True,\
                                   return_recovered_vm_list=True,\
                                   validate_network=False,\
                                   recovery_plan=rp2)

    nic_info = draas_library.get_nic_list(recovered_vms)
    STEP("Checking whether VMs came up without nics")
    nic_list = [nic for nic in nic_info if nic != []]
    pass_msg = "VMs comes out without NICs which is expected"
    fail_msg = "VMs have NICs which is unexpected "
    assert_true(not nic_list, fail_msg, pass_msg)

"""
Test RPJ type test_failover.

Copyright (c) 2017 Nutanix Inc. All rights reserved.

Author: vijayku.bellubb@nutanix.com
        sreedevi.rapaka@nutanix.com
"""
# pylint: disable = no-member

import re

from workflows.draas.draas_workflows import DraasWorkflow
from workflows.draas import draas_library
from workflows.metro.dr_lib import assert_true
from framework.lib.test.nos_test import NOSTest
from framework.lib.nulog import STEP, INFO, DEBUG
from framework.exceptions.entity_error import NuTestEntityOperationError
from framework.exceptions.nutest_error import NuTestError
from framework.hypervisors.hypervisor_types import HypervisorType

class DraasTestFailover(NOSTest):
  """This class defines test case for RPJ type rpj_type_test_failover"""

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

    create_test_subnets = self.test_args.get('create_test_subnets', True)
    self.draas_wo.do_setup(create_uvm=False, create_rp=False, \
                           create_test_subnets=create_test_subnets)
    self.snap_ids = []
    self.use_default_ipam = self.test_args.get('use_default_ipam', True)


  def teardown(self):
    """Basic teardown for each test.

    Returns:
      None.
    """
    draas_library.draas_teardown_helper([self.draas_wo],
                                        test_result_status=self.result[
                                          "result"], log_dir=self.log_dir)

  def test_verify_test_failover(self):
    """
    Metadata:
      Summary: This test performs test failover.
      Priority: $P0
      Components: [$CEREBRO]
      Services: [$AOS_TAR]
      Tags: [$AOS_DRAAS_TAR]
      Requirements: [FEAT-3429, ENG-105800, ENG-156525]
      Steps:
        - Create Categories.
        - Create VMs under the category.
        - Edit PR and add the category to the PR.
        - Trigger PR process api.
        - Create reovery plan to add all the VMs that are protected.
        - Validate the recovery plan on destination.
        - Perform RPJ of type TEST_FAILOVER on the recovery plan.
        - Verify the vlan details of brought up VMs on destination.
        - Trigger Test cleanup.
        - Create new test_subnet.
        - Update RP with new test_subnet.
        - Trigger RPJ TFO.
        - Expected Results
          - 1. Category creation should work.
          - 2. VMs creation with categories should work.
          - 3. Editing PR should work.
          - 4. VMs should be auto-protected after triggering PR process api.
          - 5. snapshot should also be replicated to remote site.
          - 6. Recovery plan creation should work and should get created with
               test network.
          - 7. Recovery plan validation should work.
          - 8. New VMs should come up on remote PC after TEST_FAILOVER.
          - 9. Verify the vlans of vms on test network, vlan of vms should
               match vlans specified in test subnet of recovery plan.
          - 10. Test cleanup should succeed.
          - 11. Test subnet must be created.
          - 12. RP should update with new test_subnet.
          - 13. TFO should success and VMs should come up with newer
                test_network.

    """
    STEP('Create Test Subnets on both source and destination')
    self.draas_wo.create_test_subnet(test_subnet_index=0)
    self.validate_network = self.test_args["validate_network"]

    STEP("Creating categories.")
    self.categories_list = self.test_args["categories"]
    self.draas_wo.create_categories(categories_list=self.categories_list)

    STEP("Creating required UVMs with categories.")
    self.draas_wo.create_uvms_with_category(self.categories_list, \
                                            use_default_ipam= \
                                            self.use_default_ipam,
                                            upgrade_esx_hardware_version=True)

    STEP("Editing Protection rule to protect UVMs in category.")
    self.draas_wo.edit_protection_rule(
      categories=self.test_args["protection_rule_categories"])

    STEP("Triggering Protection rule process api.")
    self.draas_wo.process_protection_rule(validate_snaps=True,
                                          categories_list=self.test_args
                                          ["protection_rule_categories"],
                                          calc_local_checksum=False,
                                          calc_remote_checksum=False)

    STEP("Creating Recovery plan to use categories and test subnet.")
    rp = self.draas_wo.create_recovery_plan_custom(
      recovery_plan_stages=self.test_args["recovery_plan_stages"])

    STEP("Starting Recovery.")
    self.draas_wo.start_recovery(action="VALIDATE", recovery_plan=rp)
    vm_list = self.draas_wo.start_recovery(action="TEST_FAILOVER", \
                                 recovery_plan=rp, \
                                 validate_network=\
                                   self.validate_network, \
                                 recovery_plan_stages=\
                                   self.test_args["recovery_plan_stages"], \
                                 validate_recovery_order=True, \
                                 return_recovered_vm_list=True)

    STEP("Trigger Test cleanup.")
    rpj = self.draas_wo.pc_entities[self.remote_pc.svms[0].ip] \
          [DraasWorkflow.RPJ]
    self.draas_wo.test_failover_cleanup_and_validate(self.pc_clusters[1], \
                                                     rpj, vm_list)

    STEP("Create new test_subnet.")
    test_subnet_details = {
      self.source_pc.svm_ips[0] : {self.source_pe_list[0].svm_ips[0]:
                                     self.test_args["ipam_subnet_details"]},
      self.remote_pc.svm_ips[0] : {self.remote_pe_list[0].svm_ips[0]:
                                     self.test_args["ipam_subnet_details"]}
    }
    new_port_group_name = self.test_args.get('new_port_group_name', "TestNet")
    new_port_group_vlan_id = self.test_args.get('new_port_group_vlan_id', 0)
    self.draas_wo.create_test_subnet(test_subnet_details= \
                                     test_subnet_details, \
                                     use_default_ipam=False, \
                                     test_subnet_index=0,
                                     port_group_name=new_port_group_name,
                                     port_group_vlan_id=new_port_group_vlan_id)

    STEP("Edit RP with new test subnet.")
    parameters = rp.get()["spec"]["resources"]["parameters"]
    if self.draas_wo.source_hypervisor_type == HypervisorType.ESX:
      parameters['network_mapping_list'][0] \
        ['availability_zone_network_mapping_list'][0] \
        ['test_network']["name"] = new_port_group_name
    else:
      parameters['network_mapping_list'][0] \
        ['availability_zone_network_mapping_list'][0] \
        ['test_network']["name"] = self.test_args["ipam_subnet_details"][0] \
                                   ["name"]
      parameters['network_mapping_list'][0] \
        ['availability_zone_network_mapping_list'][0] \
        ['test_network']["subnet_list"][0]["gateway_ip"] = self.test_args \
        ["ipam_subnet_details"][0]["ip_config"]["default_gateway_ip"]
      parameters['network_mapping_list'][0] \
        ['availability_zone_network_mapping_list'][0] \
        ['test_network']["subnet_list"][0]["prefix_length"] = self.test_args \
        ["ipam_subnet_details"][0]["ip_config"]["prefix_length"]

    if self.draas_wo.remote_hypervisor_type == HypervisorType.ESX:
      parameters['network_mapping_list'][0] \
        ['availability_zone_network_mapping_list'][1] \
        ['test_network']["name"] = new_port_group_name
    else:
      parameters['network_mapping_list'][0] \
        ['availability_zone_network_mapping_list'][1] \
        ['test_network']["name"] = self.test_args["ipam_subnet_details"][0] \
        ["name"]
      parameters['network_mapping_list'][0] \
        ['availability_zone_network_mapping_list'][1] \
        ['test_network']["subnet_list"][0]["gateway_ip"] = self.test_args \
        ["ipam_subnet_details"][0]["ip_config"]["default_gateway_ip"]
      parameters['network_mapping_list'][0] \
        ['availability_zone_network_mapping_list'][1] \
        ['test_network']["subnet_list"][0]["prefix_length"] = self.test_args \
        ["ipam_subnet_details"][0]["ip_config"]["prefix_length"]

    things_to_edit = {"parameters": parameters}
    self.draas_wo.edit_recovery_plan(recovery_plan=rp, **things_to_edit)

    STEP("Trigger TEST_FAILOVER.")
    self.draas_wo.start_recovery(action="TEST_FAILOVER", recovery_plan=rp, \
                                 validate_network=\
                                   self.validate_network, \
                                 recovery_plan_stages=\
                                   self.test_args["recovery_plan_stages"])

  def test_verify_tfo_after_vms_delete(self):
    """
    Metadata:
      Summary: This test performs test failover 2 times with some vms deleted
               on source the second time and expects deleted vms corresponding
               snapshots wont get recovered on remote site when test failed over
               second time.
      Priority: $P2
      Components: [$CEREBRO]
      Services: [$AOS_TAR]
      Tags: [$AOS_DRAAS_TAR]
      Requirements: [FEAT-3429, ENG-105800]
      Steps:
        - Create test subnets on source and destination.
        - Create Categories.
        - Create VMs under the category.
        - Edit PR and add the category to the PR.
        - Trigger PR process api.
        - Create reovery plan to add all the VMs that are protected.
        - Validate the recovery plan on destination.
        - Perform RPJ of type TEST_FAILOVER on the recovery plan.
        - Verify the vlan details of brought up VMs on destination.
        - Delete recovered vms on destination.
        - Delete one of the vm on source
        - Bind the source, and edit the RPO so that new snapshots gets triggered
        - Trigger PR
        - Starting Recovery again.
        - verify if deleted vms that got deleted on source, and corresponding
          snapshots are not recovered on remote.
        - Expected Results
          - 1. Category creation should work.
          - 2. VMs creation with categories should work.
          - 3. Editing PR should work.
          - 4. VMs should be auto-protected after triggering PR process api.
          - 5. snapshot should also be replicated to remote site.
          - 6. Recovery plan creation should work and should get created with
               test network.
          - 7. Recovery plan validation should work.
          - 8. New VMs should come up on remote PC after TEST_FAILOVER.
          - 9. Verify the vlans of vms on test network, vlan of vms should
               match vlans specified in test subnet of recovery plan.
          - 10. Recovered vms should get delete on remote.
          - 11. one of the source vm should get deleted.
          - 12. New snapshots also should get triggered.
          - 13. Recovery plan job execution should be successful.
          - 14. The vms that got deleted on source corresponding snapshots of it
                should not get reocvered on remote.

    """

    STEP('Create Test Subnets on both source and destination')
    self.draas_wo.create_test_subnet(test_subnet_index=0)
    self.validate_network = self.test_args["validate_network"]

    STEP("Creating categories.")
    self.categories_list = self.test_args["categories"]
    self.draas_wo.create_categories(categories_list=self.categories_list)

    STEP("Creating required UVMs with categories.")
    self.draas_wo.create_uvms_with_category(self.categories_list,
                                            dummy_vm=False,
                                            use_default_ipam=\
                                              self.use_default_ipam)

    STEP("Editing Protection rule to protect UVMs in category.")
    self.draas_wo.edit_protection_rule(
      categories=self.test_args["protection_rule_categories"])

    STEP("Triggering Protection rule process api.")
    self.draas_wo.process_protection_rule(validate_snaps=True,
                                          categories_list=self.test_args
                                          ["protection_rule_categories"])

    STEP("Creating Recovery plan to use categories and test subnet.")
    rp = self.draas_wo.create_recovery_plan_custom(
      recovery_plan_stages=self.test_args["recovery_plan_stages"])


    STEP("Starting Recovery.")
    self.draas_wo.start_recovery(action="VALIDATE", recovery_plan=rp)
    recovered_vms = self.draas_wo.\
      start_recovery(action="TEST_FAILOVER", recovery_plan=rp, \
                     validate_network=self.validate_network, \
                     validate_recovery_order=True, \
                     return_recovered_vm_list=True)

    STEP("Delete recovered vms on remote")
    DEBUG(recovered_vms)
    self.draas_wo.remove_vms(vms_list=recovered_vms,
                             clusters=self.draas_wo.remote_clusters,
                             hypervisor_type= \
                               self.draas_wo.remote_hypervisor_type)

    STEP("Delete one of the vm on source")
    self.draas_wo.delete_uvms_with_category(self.test_args["uvm_delete_list"])


    STEP("Bind the vms on source")
    self.draas_wo.bind_uvms_with_category(categories_list=\
                                          self.test_args[\
                                          "protection_rule_categories"],\
                                          action="TEST_FAILOVER")

    STEP("Edit the RPO so that new snapshots gets triggered.")
    edited_rpo = 7200
    pr_protected_cat_at_a = {}
    pr_protected_cat_at_a["edited_rpo"] = edited_rpo
    pr_protected_cat_at_a["categories"] = \
      self.test_args["protection_rule_categories"]


    STEP("Edit PR  at A to protect categories.")
    self.draas_wo.edit_protection_rule(overwrite_fields=True, \
                                       **pr_protected_cat_at_a)

    STEP("Trigger PR.")
    self.draas_wo.process_protection_rule(validate_snaps=True,
                                          categories_list=\
                                            self.test_args[\
                                              "protection_rule_categories"],
                                          calc_local_checksum=False, \
                                          calc_remote_checksum=False)

    STEP("Starting Recovery.")
    self.draas_wo.start_recovery(action="VALIDATE", recovery_plan=rp)
    recovered_vms = self.draas_wo.start_recovery(action="TEST_FAILOVER", \
                                        recovery_plan=rp, \
                                        validate_network=\
                                        self.validate_network, \
                                        validate_recovery_order=True,\
                                        return_recovered_vm_list=True)

    STEP("Verify if deleted vms on source are also recovered on remote.")
    INFO(recovered_vms)
    assert len(recovered_vms) == 1, "Test failover should not recover "\
                                    "Vms from snapshot on remote whose \
                                     corresponding vms are deleted on \
                                     source"


  def test_verify_test_failover_without_test_network(self):
    """
    Metadata:
      Summary: This test performs test failover without populating test
        subnet in recovery plan.
      Priority: $P2
      Components: [$CEREBRO]
      Services: [$AOS_TAR]
      Tags: [$AOS_DRAAS_TAR]
      Requirements: [FEAT-3429, ENG-105800]
      Steps:
        - Create Categories.
        - Create VMs under the category.
        - Edit PR and add the category to the PR.
        - Trigger PR process api.
        - Create recovery plan to add all the VMs that are protected
          but not test subnet.
        - Validate the recovery plan on destination.
        - Perform RPJ of type TEST_FAILOVER on the recovery plan.
        - Verify during test failover, proper warning is thrown like
          test subnet not found.
        - ExpectedResults
          - 1. Category creation should work.
          - 2. VMs creation with categories should work.
          - 3. Editing PR should work.
          - 4. VMs should be auto-protected after triggering PR process api.
          - 5. snapshot should also be replicated to remote site.
          - 6. Recovery plan should get created without test network.
          - 7. Recovery plan validation should work.
          - 8. Proper warning should be thrown during test failover, that test
               subnet not found.

    """

    STEP("Creating categories.")
    self.categories_list = self.test_args["categories"]
    self.draas_wo.create_categories(categories_list=self.categories_list)

    STEP("Creating required UVMs with categories.")
    self.draas_wo.create_uvms_with_category(self.categories_list,
                                            dummy_vm=False,
                                            use_default_ipam=\
                                              self.use_default_ipam)

    STEP("Editing Protection rule to protect UVMs in category.")
    self.draas_wo.edit_protection_rule(
      categories=self.test_args["protection_rule_categories"])

    STEP("Triggering Protection rule process api.")
    self.draas_wo.process_protection_rule(validate_snaps=True,
                                          categories_list=self.test_args
                                          ["protection_rule_categories"])

    STEP("Creating Recovery plan to use categories and test subnet")
    rp = self.draas_wo.create_recovery_plan_custom(
      recovery_plan_stages=self.test_args["recovery_plan_stages"])

    STEP("Starting Recovery.")
    task_uuid = self.draas_wo.trigger_rpj(action="TEST_FAILOVER",
                                          recovery_plan=rp,
                                          wait_for_completion=False,
                                          return_task_uuid=True)

    subnet_name = self.draas_wo.pc_entities[self.source_pc.svms[0].ip] \
      [self.draas_wo.SUBNET][0].name

    warning_message = "The network {} associated with one or more VMs, " \
                      "could not be mapped to any test " \
                      "network.".format(subnet_name)
    expected_task_error = "Recovery Plan validation failed"

    rp_job = self.draas_wo.pc_entities[self.draas_wo.source_pc.svms[0].ip]\
      [DraasWorkflow.RPJ]

    status = draas_library.wait_on_rpj(rp_job)
    if status == "FAILED_WITH_WARNING":
      resp = rp_job.get()
    else:
      raise  NuTestError("Test FailOver should be failed without "\
                             "test network - Status:{}".format(status))

    validation_report = resp["status"]["validation_information"]
    error_validated = draas_library.verify_warning_error_recovery_validation(
      validation_report=validation_report,
      expected_warning=warning_message)

    status = draas_library.check_error_in_task(
      self.draas_wo.remote_pc, task_uuid, "FAILED",
      expected_task_error)

    assert_true(error_validated and status,
                "Test failover failed due to unexpected error.",
                "Test failover failed as expected")

  def test_testfailover_with_delay_concurrent_poweron(self):
    """
    Metadata:
      Summary: This test performs test failover having mutiple VMs in each
               stage, also verifies concurrent poweron and also with delay
               between each stage.
      Priority: $P1
      Components: [$CEREBRO]
      Services: [$AOS_TAR]
      Tags: [$AOS_DRAAS_TAR]
      Requirements: [FEAT-3429, ENG-105800]
      Steps:
        - Create 2 Categories with 2 VMs in each category.
        - Create VMs under both the category.
        - Edit PR and add the categories to the PR.
        - Trigger PR process api.
        - Create reovery plan to add all the VMs that are protected.
        - Validate the recovery plan on destination.
        - Perform RPJ of type TEST_FAILOVER on the recovery plan.
        - verify if concurrent powering on VMs happen for VMs in same stage.
        - Verify the vlan details of brought up VMs on destination.
        - Expected Results
          - 1. Category creation should work.
          - 2. VMs creation with categories should work.
          - 3. Editing PR should work.
          - 4. VMs should be auto-protected after triggering PR process api.
          - 5. snapshot should also be replicated to remote site.
          - 6. Recovery plan creation should work and should get created with
               test network.
          - 7. Recovery plan validation should work.
          - 8. VMs in same stage should poweron concurrently.
          - 9. Verify the vlans of vms on test network, vlan of vms should
               match vlans specified in test subnet of recovery plan.

    """

    STEP('Create Test Subnets on both source and destination')
    self.draas_wo.create_test_subnet(test_subnet_index=0)
    self.validate_network = self.test_args["validate_network"]

    STEP("Creating categories.")
    self.categories_list = self.test_args["categories"]
    self.draas_wo.create_categories(categories_list=self.categories_list)

    STEP("Creating required UVMs with categories.")
    self.draas_wo.create_uvms_with_category(self.categories_list,
                                            dummy_vm=False,
                                            use_default_ipam=\
                                              self.use_default_ipam)

    STEP("Editing Protection rule to protect UVMs in category.")
    self.draas_wo.edit_protection_rule(
      categories=self.test_args["protection_rule_categories"])

    STEP("Triggering Protection rule process api.")
    self.draas_wo.process_protection_rule(validate_snaps=True,
                                          categories_list=self.test_args
                                          ["protection_rule_categories"])

    STEP("Create recovery plan with 2 stages, with 2 UVMs in each stage and" \
         "test subnet")
    rp = self.draas_wo.create_recovery_plan_custom(
      recovery_plan_stages=self.test_args["recovery_plan_stages"])

    STEP("Start recovery and validate entity recovery on remote.")
    self.draas_wo.start_recovery(action='TEST_FAILOVER', recovery_plan=rp,
                                 recovery_plan_stages=self.test_args[
                                   'recovery_plan_stages'],
                                 validate_recovery_order=True)

  def test_tfo_test_network_deleted(self):
    """
      Raises:
        NuTestError: If the Recovery plan creates succesfully
     Metadata:
        Summary: Test failover with test network deleted from remote PE.
        Priority: $P2
        Components: [$CEREBRO]
        Services: [$AOS_TAR]
        Tags: [$AOS_DRAAS_TAR]
        Requirements: [FEAT-3429, ENG-106961, ENG-121603]
        Steps:
         - Create test subnet on both source and remote.
         - Create UVM with category.
         - Protect the VM using Protection rule.
         - Create Recovery Plan with non-existing network on remote.
         - Create Recovery Plan with proper network on remote.
         - Delete test NW from the remote PE.
         - Start recovery on remote PC.
         - ExpectedResults
           - 1. Test subnet creation should succeed.
           - 2. VM creation should succeed.
           - 3. VM Protection should succeed.
           - 4. Recovery Plan creation should fail.
           - 5. Recovery Plan creation should succeed.
           - 6. Deleting test NW should succeed.
           - 7. Recovery Plan Job must be executed and VM should come up
                without test network.

      """
    STEP('Create Test Subnets on both source and destination.')
    self.draas_wo.create_test_subnet(test_subnet_index=0)

    STEP("Creating required UVMs with categories.")
    self.categories_list = self.test_args["categories"]
    self.draas_wo.create_categories(categories_list=self.categories_list)
    self.draas_wo.create_uvms_with_category(self.categories_list,
                                            use_default_ipam=\
                                              self.use_default_ipam)

    STEP("Protect the VM using Protection rule.")
    INFO("Editing Protection rule to protect UVMs in category.")
    things_to_edit = {}
    things_to_edit["categories"] = self.test_args["protection_rule_categories"]
    self.draas_wo.edit_protection_rule(**things_to_edit)

    INFO("Triggering Protection rule process api.")
    self.draas_wo.process_protection_rule(categories_list=self.test_args
                                          ["protection_rule_categories"],
                                          validate_snaps=True,
                                          calc_remote_checksum=False,
                                          calc_local_checksum=False)

    STEP("Create Recovery Plan with non-existing network on remote.")
    try:
      _ = self.draas_wo. \
      create_recovery_plan_custom(recovery_plan_stages=\
      self.test_args["recovery_plan_stages"],\
      source_subnet_name=self.test_args["non-existent_subnet_name"])
      raise  NuTestError("Recovery plan created succesfully which"\
                             "is unexpected")
    except (NuTestEntityOperationError, NuTestError) as error:
      error_msg = "Failed to create the entity"
      pass_msg = "Recovery plan creation failed with"\
                      "non existing network on remote as expected"
      fail_msg = "Recovery plan creation with non"\
                    "existing network on remote passed which is unexpected"
      INFO(error)
      assert_true(error_msg in str(error), fail_msg, pass_msg)

    STEP("Create Recovery Plan with proper network on remote.")
    rp = self.draas_wo.\
          create_recovery_plan_custom(recovery_plan_stages=\
          self.test_args["recovery_plan_stages"])

    INFO("Validate recovery plan")
    self.draas_wo.start_recovery(action="VALIDATE", validate_network=False)

    STEP("Delete test NW from the remote PE.")
    self.draas_wo.pc_entities[self.remote_pc.svms[0].ip]\
      ['test_subnet_name'][0].remove()

    STEP("Starting TEST_FAILOVER recovery")
    vm_recovery_list = self.draas_wo.start_recovery(action='TEST_FAILOVER',\
                         recovery_plan=rp, recovery_plan_stages=\
                         self.test_args['recovery_plan_stages'],\
                         validate_recovery_order=True, force=True,\
                         validate_network=False)
    INFO("Recovered vm list : %s" %vm_recovery_list)
    vm_name_list = [vm_recovery_list[0]['entity_list'][i]['name'] \
      for i in range(len(vm_recovery_list[0]['entity_list']))]
    vm_object_list \
      = draas_library.get_vm_object_list_by_name(vm_name_list,\
        self.remote_pe_list[0])
    nic_lists = [vm.get_nics() for vm in vm_object_list]

    fail_msg = "Recovered VM still have NICs(subnets) which is unexpected"
    pass_msg = "Recovered VM doesn't have NICs(subnets) as expected"
    for nic_list in nic_lists:
      assert_true(nic_list == [], fail_msg, pass_msg)

  def test_network_failure_while_rp_execution_in_progress(self):
    """
      Metadata:
        Summary: Verify the network failure while recovery
           plan execution inprogress.
        Priority: $P2
        Components: [$CEREBRO]
        Services: [$AOS_TAR]
        Tags: [$AOS_DRAAS_TAR]
        Requirements: [FEAT-3429, ENG-121603]
        Steps:
          - 1. Create test subnets on both source and destination
          - 2. Creating categories.
          - 3. Create a VM.
          - 4. Create PR with above category.
          - 5. Create RP with 3 stages (1 VMs each) with NW mapping.
          - 6. Delete test NW from the remote PE.
          - 7. Start TEST_FAILOVER recovery.
          - ExpectedResults
            - 1. Test subnet creation should succeed.
            - 2. VM creation should succeed.
            - 3. VM Protection should succeed.
            - 4. Recovery Plan creation should succeed.
            - 5. Deleting test NW should succeed.
            - 6. Recovery Plan Job must be executed and VM should come up
                without test network.

    """
    STEP('Create Test Subnets on both source and destination.')
    self.draas_wo.create_test_subnet(test_subnet_index=0)

    STEP("Creating required UVMs with categories.")
    self.categories_list = self.test_args["categories"]
    self.draas_wo.create_categories(categories_list=self.categories_list)
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

    STEP("Create Recovery Plan with three stages")
    rp = self.draas_wo.\
          create_recovery_plan_custom(recovery_plan_stages=\
          self.test_args["recovery_plan_stages"])

    STEP("Validate TEST_FAILOVER recovery")
    self.draas_wo.start_recovery(action="VALIDATE", validate_network=False)

    STEP("Delete test NW from the remote PE.")
    self.draas_wo.pc_entities[self.remote_pc.svms[0].ip]\
      ['test_subnet_name'][0].remove()

    STEP("Starting TEST_FAILOVER recovery")
    vm_recovery_list = self.draas_wo.start_recovery(action='TEST_FAILOVER',\
                                                   recovery_plan=rp,\
                                                 validate_recovery_order=True,\
                                                   force=True,\
                                                   validate_network=False)

    INFO("Recovered vm list : %s" %vm_recovery_list)
    vm_name_list = [vm_recovery_list[0]['entity_list'][i]['name'] \
      for i in range(len(vm_recovery_list[0]['entity_list']))]
    vm_object_list \
      = draas_library.get_vm_object_list_by_name(vm_name_list,\
        self.remote_pe_list[0])
    nic_lists = [vm.get_nics() for vm in vm_object_list]

    fail_msg = "Recovered VM still have NICs(subnets) which is unexpected"
    pass_msg = "Recovered VM doesn't have NICs(subnets) as expected"
    for nic_list in nic_lists:
      assert_true(nic_list == [], fail_msg, pass_msg)

  def test_verify_test_failover_explicit_vms(self):
    """
    Metadata:
      Summary: This test performs test failover with explicit vms and verifies
        RP is not updated with new vm uuids and new RP is not created.
      Priority: $P1
      Components: [$CEREBRO]
      Services: [$AOS_TAR]
      Tags: [$AOS_DRAAS_TAR]
      Requirements: [FEAT-3429, ENG-105800, ENG-149394]
      Steps:
        - Create Categories.
        - Create VMs under the category.
        - Edit PR and add the category to the PR.
        - Trigger PR process api.
        - Create recovery plan to add all the VMs that are protected.
        - Validate the recovery plan on destination.
        - Perform RPJ of type TEST_FAILOVER on the recovery plan.
        - Verify the vlan details of brought up VMs on destination.
        - Verify after test failover the rp is not updated with
          new vm uuids and new RP is not created.
        - Expected Results
          - 1. Category creation should work.
          - 2. VMs creation with categories should work.
          - 3. Editing PR should work.
          - 4. VMs should be auto-protected after triggering PR process api.
          - 5. snapshot should also be replicated to remote site.
          - 6. Recovery plan creation should work and should get created with
               test network.
          - 7. Recovery plan validation should work.
          - 8. New VMs should come up on remote PC after TEST_FAILOVER.
          - 9. Verify the vlans of vms on test network, vlan of vms should
               match vlans specified in test subnet of recovery plan.
          - 10. RP should not get updated with new vm uuids and new RP should
                not get created.

    """

    STEP('Create Test Subnets on both source and destination')
    self.draas_wo.create_test_subnet(test_subnet_index=0)
    self.validate_network = self.test_args["validate_network"]

    STEP("Creating categories.")
    self.categories_list = self.test_args["categories"]
    self.draas_wo.create_categories(categories_list=self.categories_list)

    STEP("Creating required UVMs with categories.")
    self.draas_wo.create_uvms_with_category(self.categories_list,
                                            dummy_vm=False,
                                            use_default_ipam=\
                                              self.use_default_ipam)

    STEP("Editing Protection rule to protect UVMs in category.")
    self.draas_wo.edit_protection_rule(
      categories=self.test_args["protection_rule_categories"])

    STEP("Triggering Protection rule process api.")
    self.draas_wo.process_protection_rule(validate_snaps=True,
                                          categories_list=self.test_args
                                          ["protection_rule_categories"],
                                          calc_local_checksum=False,
                                          calc_remote_checksum=False)

    STEP("Creating Recovery plan.")
    rp = self.draas_wo.create_recovery_plan_custom(
      recovery_plan_stages=self.test_args["recovery_plan_stages"])

    STEP("Starting Recovery.")
    self.draas_wo.start_recovery(action="VALIDATE", recovery_plan=rp)
    try:
      self.draas_wo.start_recovery(
        action="TEST_FAILOVER", recovery_plan=rp,
        validate_network=self.validate_network,
        recovery_plan_stages=self.test_args["recovery_plan_stages"],
        validate_rp_after_upfo=False)
    except NuTestError as exc:
      pattern = re.compile(r"VM uuid: [0-9a-zA-Z_-]* in recovery plan {0} "
                           r"after unplanned failover is not in "
                           r"recovered vm list".format(rp.name))
      pass_msg = "RP is not updated with new vm uuids after TFO."
      fail_msg = "RP is updated with new vm uuids after TFO, this is " \
                 "unexpected."
      assert_true(pattern.search(str(exc)), fail_msg, pass_msg)

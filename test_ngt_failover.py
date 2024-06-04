"""TEST FAILOVER for NGT.

Copyright (c) 2018 Nutanix Inc. All rights reserved.

Author: sreedevi.rapaka@nutanix.com
"""
# pylint: disable=no-member
# pylint: disable=maybe-no-member
# pylint: disable=unused-import
# pylint: disable=unpacking-non-sequence
# pylint: disable=unbalanced-tuple-unpacking
# pylint: disable=protected-access
# pylint: disable = too-many-locals
# pylint: disable = too-many-statements
# pylint: disable = too-many-lines

import datetime
import time
import copy
import re
from framework.components.cerebro import Cerebro
from framework.components.magneto import Magneto
from framework.lib.test.nos_test import NOSTest
from framework.lib.nulog import STEP, INFO, DEBUG
from framework.lib.parallel_executor import ParallelExecutor
from framework.interfaces.interface import Interface
from framework.entities.protection_domain.protection_domain import \
  ProtectionDomain
from framework.exceptions.entity_error import NuTestEntityOperationError
from framework.exceptions.nutest_error import NuTestError
from framework.entities.vm_recovery_point.vm_recovery_point import \
  VmRecoveryPoint
from framework.entities.vm.vm import Vm
from framework.entities.task.task import Task
from framework.operating_systems.file_path.file_path import FilePath
from framework.interfaces.rest.prism_client import PrismRestVersion
from framework.interfaces.rest.prism_client import PrismClient
from framework.entities.remote_site.remote_site import RemoteSite
from workflows.draas.draas_workflows import DraasWorkflow
from workflows.draas import draas_library
from workflows.metro.dr_lib import assert_true
from workflows.draas.group.group import Group
from workflows.async_dr.async_dr_library import detach_cdrom, attach_cdrrom, \
  get_vm_objects_by_name, teardown_helper, install_ngt_on_vms, \
  is_ngt_running_in_vm

class NgtTestFailover(NOSTest):
  """Test suite for Test Failover with NGT.
  """
  def setup(self):
    """
    Setup method for Test Failover with NGT.
    """
    self.pe_clusters = self.get_resources_by_type(self.NOS_CLUSTER)
    self.pc_clusters = self.get_resources_by_type(self.PRISM_CENTRAL)

    self.local_cluster = self.pe_clusters[0]

    pc_pe_map = draas_library.get_pc_pe_map(self.pe_clusters, self.pc_clusters)
    (self.source_pc, self.source_pe_list, self.remote_pc, self.remote_pe_list) \
      = draas_library.get_source_remote_map(self.pc_clusters, pc_pe_map)
    self.setup_ngt_on_xi = self.test_args.get("setup_ngt_on_xi", False)
    cleanup_entities = self.test_args.get("cleanup_entities", True)
    self.draas_wo = DraasWorkflow(source_clusters=self.source_pe_list[0],
                                  interface=self.interface_type,
                                  source_pc=self.source_pc,
                                  remote_clusters=self.remote_pe_list[0],
                                  remote_pc=self.remote_pc,
                                  cleanup_existing_entities=cleanup_entities,
                                  setup_ngt_on_xi=self.setup_ngt_on_xi)

  def teardown(self):
    """Teardown for Test Failover with NGT.
    """
    draas_library.draas_teardown_helper([self.draas_wo],
                                        test_result_status=self.result[
                                          "result"], log_dir=self.log_dir,
                                        unset_ngt_gflags_on_xi=
                                        self.setup_ngt_on_xi)

  def test_ngt_test_failover(self, pointintime=False):
    """
      Args:
        pointintime(bool) : To use point in time snapshot during recovery.
        Defaults to False.

     Metadata:
       Summary: This test performs Test Failover with NGT from latest snapshot
       Priority: $P2
       Components: [$CEREBRO]
       Services: [$AOS_TAR]
       Tags: [$AOS_DRAAS_TAR]
       Requirements: [FEAT-3429, ENG-105800, ENG-121603]
       Steps:
         - Create test subnet on both source and remote.
         - Create UVM with category.
         - Protect the VM using Protection rule.
         - Install NGT on VM.
         - Create Recovery Plan.
         - Start recovery on remote PC from latest snapshot.
         - Verify NGT status of recovered VM.
         - ExpectedResults
           - 1. Test subnet creation should succeed.
           - 2. VM creation should succeed.
           - 3. VM Protection should succeed.
           - 4. NGT installation should succeed.
           - 5. Recovery Plan creation should succeed.
           - 6. Recovery Plan Job must be executed.
           - 7. NGT should be enabled on recovered VM.

     """
    STEP("Do DRaaS setup.")
    self.entities = self.draas_wo.do_setup(create_uvm=False, create_rp=False,\
                    create_pr=False)

    STEP('Create Test Subnets on both source and destination')
    self.draas_wo.create_test_subnet(test_subnet_index=0)

    STEP("Creating required UVMs.")
    self.categories_list = self.test_args["categories"]
    self.draas_wo.create_categories(categories_list=self.categories_list)

    things_to_edit = {}
    things_to_edit["image"] = self.test_args.get("image", None)
    things_to_edit["image_name"] = self.test_args.get("image_name", None)
    self.draas_wo.create_uvms_with_category(self.categories_list,
                                            return_vm_list=True,
                                            use_default_ipam=False,
                                            install_ngt=True, **things_to_edit)

    STEP("Protect the VM using Protection rule")
    pr = self.draas_wo.create_protection_rule(pr_name="NutestPR")

    INFO("Editing Protection rule to protect UVMs in category.")
    things_to_edit = {}
    things_to_edit["categories"] = self.test_args["protection_rule_categories"]
    self.draas_wo.edit_protection_rule(protection_rule=pr, **things_to_edit)

    INFO("Triggering Protection rule process api.")
    self.draas_wo.process_protection_rule(categories_list=self.test_args
                                          ["protection_rule_categories"],
                                          calc_remote_checksum=False,
                                          calc_local_checksum=False,
                                          validate_snaps=True)

    STEP("Creating Recovery plan to use categories.")
    rp = self.draas_wo.create_recovery_plan_custom(recovery_plan_stages=\
           self.test_args["recovery_plan_stages"])

    if pointintime:
      INFO("Specify point of time from which snapshot must be taken.")
      recovery_reference_time = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                              time.gmtime())

      STEP("Create oob snapshot")
      self.draas_wo.create_oob_snapshot()

      STEP("Starting TEST_FAILOVER recovery from the point in time snapshot")
      self.draas_wo.start_recovery(action="VALIDATE")
      vm_recovery_list = self.draas_wo.start_recovery(action='FAILOVER',\
                           recovery_plan=rp, recovery_plan_stages=\
                           self.test_args['recovery_plan_stages'],\
                           recovery_reference_time=recovery_reference_time,\
                           validate_recovery_order=True)
    else:
      STEP("Starting TEST_FAILOVER recovery")
      self.draas_wo.start_recovery(action="VALIDATE")
      vm_recovery_list = self.draas_wo.start_recovery(action='TEST_FAILOVER',\
                           recovery_plan=rp, recovery_plan_stages=\
                           self.test_args['recovery_plan_stages'],\
                           validate_recovery_order=True)

    DEBUG(vm_recovery_list)

    STEP("Verify NGT status of recovered VM.")
    INFO("Get VM objects from VM recovery list.")
    vm_name_list = draas_library.get_vms_from_recovery_list(vm_recovery_list)
    vm_object_list \
      = draas_library.get_vm_object_list_by_name(vm_name_list,\
        self.remote_pe_list[0])

    INFO("Check NGT status of VM.")
    ngt_status = draas_library.is_ngt_running_in_vm(self.remote_pe_list[0],\
                   vm_object_list)
    pass_msg = "NGT enabled on recovered UVM as expected"
    fail_msg = "NGT not enabled on recovered UVM"
    assert_true(ngt_status, fail_msg, pass_msg)

  def test_ngt_test_failover_pointintime(self):
    """
     Metadata:
       Summary: This test performs Test Failover with NGT from specific point
                in snapshot
       Priority: $P2
       Components: [$CEREBRO]
       Services: [$AOS_TAR]
       Tags: [$DEPRECATED, $AOS_DRAAS_TAR]
       Requirements: [FEAT-3429, ENG-105800, ENG-121603]
       Steps:
         - Create test subnet on both source and remote.
         - Create UVM with category.
         - Protect the VM using Protection rule.
         - Install NGT on VM.
         - Create Recovery Plan.
         - Start recovery on remote PC from specific point snapshot.
         - Verify NGT status of recovered VM.
         - ExpectedResults
           - 1. Test subnet creation should succeed.
           - 2. VM creation should succeed.
           - 3. VM Protection should succeed.
           - 4. NGT installation should succeed.
           - 5. Recovery Plan creation should succeed.
           - 6. Recovery Plan Job must be executed.
           - 7. NGT should be enabled on recovered VM.

    """
    self.test_ngt_test_failover(pointintime=True)

from django.http import *
from django.core.urlresolvers import reverse
import os
import sys
from vt_plugin.models import *
from vt_manager.communication.utils.XmlHelper import *
from vt_plugin.utils.ServiceThread import *
from vt_plugin.utils.Translator import *
from vt_plugin.controller.dispatchers.ProvisioningDispatcher import ProvisioningDispatcher
from expedient.common.messaging.models import DatedMessage
from vt_plugin.controller.vtAggregateController import vtAggregateController
from vt_plugin.models.VtPlugin import VtPlugin
from expedient.clearinghouse.project.models import Project

class ProvisioningResponseDispatcher():

    '''
    Handles all the VT AM vm provisioning responses and all the actions that go 
    from the VT AM to the VT Plugin
    '''

    @staticmethod
    def processResponse(response):
        print "Entra en processResponse\n"
        for action in response.action:

            #if Action.objects.filter(uuid = action.id).exists():
            if Action.objects.filter(uuid = action.id):
                #actionModel is an instance to the action stored in DB with uuid the same as the incomming action
                actionModel = Action.objects.get(uuid = action.id)
            else:                
                actionModel =Translator.ActionToModel(action, "provisioning", save = "noSave")
                #TODO adapt code in order to enter "if" when received SUCCESS status from actions generated by island manager
                actionModel.status = 'QUEUED' #this state is just to enter de if later
                actionModel.vm = VM.objects.get(uuid = action.server.virtual_machines[0].uuid)
                
            if actionModel.status is 'QUEUED' or 'ONGOING':                
                print "The response is:"
                print actionModel
                print actionModel.uuid
                print "actionModel.status = %s" %actionModel.status

                #update action status in DB
                actionModel.status = action.status
                print "The action.status is %s" %action.status
                print "The action.description is %s" %action.description
                actionModel.description = action.description
                actionModel.save()
                
                #according to incoming action response we do update the vm state
                if actionModel.status == 'SUCCESS':
                    if actionModel.type == 'create':
                        actionModel.vm.setState('created (stopped)')
                        actionModel.vm.save()
                    elif actionModel.type == 'start' or actionModel.type == 'reboot':
                        actionModel.vm.setState('running')
                        actionModel.vm.save()                        
                    elif actionModel.type == 'hardStop':
                        actionModel.vm.setState('stopped')
                        actionModel.vm.save()
                    elif actionModel.type == 'delete':
                        actionModel.vm.completeDelete()

                    if actionModel.description == None: 
                        actionModel.description = "" 
                    else: 
                        actionModel.description = ": "+actionModel.description
                    if actionModel.requestUser:
                        DatedMessage.objects.post_message_to_user(
                                "Action %s on VM %s succeed %s" % (actionModel.type, actionModel.vm.name, actionModel.description),
                                actionModel.requestUser, msg_type=DatedMessage.TYPE_SUCCESS,
                            )
                    else:
                        project = Project.objects.get(uuid=actionModel.vm.getProjectId())
                        for user in project.members_as_permittees.all():
                            DatedMessage.objects.post_message_to_user(
                                "Action %s on VM %s succeed %s" % (actionModel.type, actionModel.vm.name, actionModel.description),
                                user, msg_type=DatedMessage.TYPE_SUCCESS,
                            )

                elif actionModel.status == 'FAILED':
                    if actionModel.description == None:     
                        actionModel.description = ""    
                    else:    
                        actionModel.description = ": "+actionModel.description

                    if actionModel.requestUser:
                        DatedMessage.objects.post_message_to_user(
                                "Action %s on VM %s failed: %s" % (actionModel.type, actionModel.vm.name, actionModel.description),
                                actionModel.requestUser, msg_type=DatedMessage.TYPE_ERROR,
                            )
                    else:
                        project = Project.objects.get(uuid=actionModel.vm.getProjectId())
                        for user in project.members_as_permittees.all():
                            DatedMessage.objects.post_message_to_user(
                                "Action %s on VM %s failed: %s" % (actionModel.type, actionModel.vm.name, actionModel.description),
                                user, msg_type=DatedMessage.TYPE_ERROR,
                            )


                    if actionModel.type == 'start':
                        actionModel.vm.setState('stopped')
                        actionModel.vm.save()
                    elif actionModel.type == 'hardStop':
                        actionModel.vm.setState('running')
                        actionModel.vm.save()
                    elif actionModel.type == 'reboot':
                        actionModel.vm.setState('stopped')
                        actionModel.vm.save()
                    elif actionModel.type == 'create':
                        ProvisioningDispatcher.cleanWhenFail(actionModel.vm, VTServer.objects.get(uuid = actionModel.vm.serverID))
                    else:
                        actionModel.vm.setState('failed')
                        actionModel.vm.save()


                elif actionModel.status == 'ONGOING':
                    if actionModel.type == 'create':
                        actionModel.vm.setState('creating...')
                        actionModel.vm.save()
                        vtplugin = VtPlugin.objects.get(id=actionModel.vm.aggregate_id)
                        projectUUID = actionModel.vm.projectId
                        sliceUUID = actionModel.vm.sliceId
                        vtAggregateController.askForAggregateResources(vtplugin,projectUUID,sliceUUID)	

                    elif actionModel.type == 'start':
                        actionModel.vm.setState('starting...')
                        actionModel.vm.save()
                    elif actionModel.type == 'hardStop':
                        actionModel.vm.setState('stopping...')
                        actionModel.vm.save()
                    elif actionModel.type == 'delete':
                        actionModel.vm.setState('deleting...')
                        actionModel.vm.save()
                    elif actionModel.type == 'reboot':
                        actionModel.vm.setState('rebooting...')
                        actionModel.vm.save()

                    #if actionModel.requestUser:
                    #    DatedMessage.objects.post_message_to_user(
                    #            "Action %s on VM %s succeed: %s" % (actionModel.type, actionModel.vm.name, actionModel.description),
                    #            actionModel.requestUser, msg_type=DatedMessage.TYPE_SUCCESS,
                    #        )
                    #else:
                    #    project = Project.objects.get(uuid=actionModel.vm.getProjectId())
                    #    for user in project.members_as_permittees.all():
                    #        DatedMessage.objects.post_message_to_user(
                    #            "Action %s on VM %s succeed: %s" % (actionModel.type, actionModel.vm.name, actionModel.description),
                    #            user, msg_type=DatedMessage.TYPE_SUCCESS,
                    #        )

                else:                    
                    actionModel.vm.setState('unknown')
                    actionModel.vm.save()
                
                    #if actionModel.requestUser:
                    #    DatedMessage.objects.post_message_to_user(
                    #            "Action %s on VM %s succeed: %s" % (actionModel.type, actionModel.vm.name, actionModel.description),
                    #            actionModel.requestUser, msg_type=DatedMessage.TYPE_SUCCESS,
                    #        )
                    #else:
                    #    project = Project.objects.get(uuid=actionModel.vm.getProjectId())
                    #    for user in project.members_as_permittees.all():
                    #        DatedMessage.objects.post_message_to_user(
                    #            "Action %s on VM %s succeed: %s" % (actionModel.type, actionModel.vm.name, actionModel.description),
                    #            user, msg_type=DatedMessage.TYPE_SUCCESS,
                    #        )
                return "Done Response"

            else:
                try:
                    raise Exception
                except Exception as e:
                    print e
                    return
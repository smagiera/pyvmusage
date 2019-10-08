#!/usr/bin/env python
"""
Python program that generates various statistics for one or more virtual machines

A list of virtual machines can be provided as a comma separated list.
"""

from __future__ import print_function
from pyVim.connect import SmartConnectNoSSL, Disconnect
from pyVmomi import vmodl, vim
from datetime import timedelta, datetime
from jinja2 import Template

import argparse
import atexit
import getpass

import ssl

vm_objects = []
interval = 360

class VM:
    def __init__(self, name, cpu_num, cpu_avg, cpu_max, mem_size, mem_avg, mem_max, c_free):
        self.name = name
        self.cpu_num = cpu_num
        self.cpu_avg = cpu_avg
        self.cpu_max = cpu_max
        self.mem_size = mem_size
        self.mem_avg = mem_avg
        self.mem_max = mem_max
        self.c_free = c_free

def GetArgs():
    """
    Supports the command-line arguments listed below.
    """
    parser = argparse.ArgumentParser(
        description='Process args for retrieving all the Virtual Machines')
    parser.add_argument('-s', '--host', required=True, action='store',
                        help='Remote host to connect to')
    parser.add_argument('-o', '--port', type=int, default=443, action='store',
                        help='Port to connect on')
    parser.add_argument('-u', '--user', required=True, action='store',
                        help='User name to use when connecting to host')
    parser.add_argument('-p', '--password', required=False, action='store',
                        help='Password to use when connecting to host')
    args = parser.parse_args()
    return args


def BuildQuery(content, vchtime, counterId, instance, vm, interval):
    perfManager = content.perfManager
    metricId = vim.PerformanceManager.MetricId(counterId=counterId, instance=instance)
    startTime = vchtime - timedelta(days=30)
    endTime = vchtime
    query = vim.PerformanceManager.QuerySpec(entity=vm, metricId=[metricId], startTime=startTime,
                                             endTime=endTime)
    perfResults = perfManager.QueryPerf(querySpec=[query])
    if perfResults:
        return perfResults
    else:
        print('ERROR: Performance results empty.  TIP: Check time drift on source and vCenter server')
        print('Troubleshooting info:')
        print('vCenter/host date and time: {}'.format(vchtime))
        print('Start perf counter time   :  {}'.format(startTime))
        print('End perf counter time     :  {}'.format(endTime))
        print(query)
        exit()


def ListVms(content):
    """
    Iterate through all datacenters and list VM info.
    """

    listofvms = []
    children = content.rootFolder.childEntity
    for child in children:  # Iterate though DataCenters
        dc = child
        #data[dc.name] = {}  # Add data Centers to data dict
        clusters = dc.hostFolder.childEntity
        for cluster in clusters:  # Iterate through the clusters in the DC
            # Add Clusters to data dict
            #data[dc.name][cluster.name] = {}
            hosts = cluster.host  # Variable to make pep8 compliance
            for host in hosts:  # Iterate through Hosts in the Cluster
                hostname = host.summary.config.name
                # Add VMs to data dict by config name
                #data[dc.name][cluster.name][hostname] = {}
                vms = host.vm
                for vm in vms:  # Iterate through each VM on the host
                    listofvms.append(vm.summary.config.name)
    return listofvms

def StatCheck(perf_dict, counter_name):
    counter_key = perf_dict[counter_name]
    return counter_key


def GetProperties(content, viewType, props, specType):
    # Build a view and get basic properties for all Virtual Machines
    objView = content.viewManager.CreateContainerView(content.rootFolder, viewType, True)
    tSpec = vim.PropertyCollector.TraversalSpec(name='tSpecName', path='view', skip=False, type=vim.view.ContainerView)
    pSpec = vim.PropertyCollector.PropertySpec(all=False, pathSet=props, type=specType)
    oSpec = vim.PropertyCollector.ObjectSpec(obj=objView, selectSet=[tSpec], skip=False)
    pfSpec = vim.PropertyCollector.FilterSpec(objectSet=[oSpec], propSet=[pSpec], reportMissingObjectsInResults=False)
    retOptions = vim.PropertyCollector.RetrieveOptions()
    totalProps = []
    retProps = content.propertyCollector.RetrievePropertiesEx(specSet=[pfSpec], options=retOptions)
    totalProps += retProps.objects
    while retProps.token:
        retProps = content.propertyCollector.ContinueRetrievePropertiesEx(token=retProps.token)
        totalProps += retProps.objects
    objView.Destroy()
    # Turn the output in retProps into a usable dictionary of values
    gpOutput = []
    for eachProp in totalProps:
        propDic = {}
        for prop in eachProp.propSet:
            propDic[prop.name] = prop.val
        propDic['moref'] = eachProp.obj
        gpOutput.append(propDic)
    return gpOutput

def create_vm_object(name, vm, content, vchtime, interval, perf_dict, ):
    statInt = 360
    cpuNum = vm.summary.config.numCpu
    memSize = vm.summary.config.memorySizeMB
    disks = vm.summary.vm.guest.disk
    #CPU Usage
    statCpuUsage = BuildQuery(content, vchtime, (StatCheck(perf_dict, 'cpu.usage.average')), "", vm, interval)
    cpuUsageLen = len(statCpuUsage[0].value[0].value)
    cpuUsage = int(((sum(statCpuUsage[0].value[0].value) / cpuUsageLen) / 100))
	#CPU Usage Max
    statCpuUsageMax = BuildQuery(content, vchtime, (StatCheck(perf_dict, 'cpu.usage.average')), "", vm, interval)
    cpuUsageMax = int(max(statCpuUsage[0].value[0].value)/100)
	#RAM
    statMemoryUsage = BuildQuery(content, vchtime, (StatCheck(perf_dict, 'mem.usage.average')), "", vm, interval)
    memoryUsageLen = len(statMemoryUsage[0].value[0].value)
    memoryUsage = int(((sum(statMemoryUsage[0].value[0].value) / memoryUsageLen) / 100))
	#RAM Max
    statMemoryUsageMax = BuildQuery(content, vchtime, (StatCheck(perf_dict, 'mem.usage.average')), "", vm, interval)
    memoryUsageMax = int(max(statMemoryUsage[0].value[0].value)/100)
    #disk usage
    c_free = ''
    for disk in disks:
        if disk.diskPath == 'C:\\' or disk.diskPath == '/':
            c_free = int(((disk.freeSpace / 1024) / 1024))
    return VM(name, cpuNum, cpuUsage, cpuUsageMax, memSize, memoryUsage, memoryUsageMax, c_free)
    


def render_html(vms_list):
    vms_list.sort(key=lambda x: x.cpu_num)
    f = open('template.html', 'r')
    contents = f.read()
    t = Template(contents)
    f.close()
    output = open('output.html', 'w+')
    output.write(t.render(items=vms_list))
    output.close()



def main():
    args = GetArgs()
    if args.password:
        password = args.password
    else:
        password = getpass.getpass(prompt='Enter password for host %s and '
                                   'user %s: ' % (args.host, args.user))

    si = SmartConnectNoSSL(host=args.host,
                           user=args.user,
                           pwd=password,
                           port=int(args.port))
    if not si:
        print("Could not connect to the specified host using specified "
              "username and password")
        return -1
    
    atexit.register(Disconnect, si)

    content = si.RetrieveContent()
    vmnames = ListVms(content)
    # Get vCenter date and time for use as baseline when querying for counters
    vchtime = si.CurrentTime()
    # Get all the performance counters
    perf_dict = {}
    perfList = content.perfManager.perfCounter
    for counter in perfList:
        counter_full = "{}.{}.{}".format(counter.groupInfo.key, counter.nameInfo.key, counter.rollupType)
        perf_dict[counter_full] = counter.key

    retProps = GetProperties(content, [vim.VirtualMachine], ['name', 'runtime.powerState'], vim.VirtualMachine)

        #Find VM supplied as arg and use Managed Object Reference (moref) for the PrintVmInfo
    for vm in retProps:
        if (vm['name'] in vmnames) and (vm['runtime.powerState'] == "poweredOn"):
            #PrintVmInfo(vm['moref'], content, vchtime, interval, perf_dict)
            print(create_vm_object(vm['name'], vm['moref'], content, vchtime, interval, perf_dict))
            vm_objects.append(create_vm_object(vm['name'], vm['moref'], content, vchtime, interval, perf_dict))
        elif vm['name'] in vmnames:
            vm_objects.append(VM(vm['name'], 999, None, None, None, None, None, None))
            #print('ERROR: Problem connecting to Virtual Machine.  {} is likely powered off or suspended'.format(vm['name']))

    render_html(vm_objects)
    return 0

# Start program
if __name__ == "__main__":
    main()

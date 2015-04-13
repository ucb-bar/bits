# Code to parse benchmark configuration files

# Contributors:
# Joao Carreira <joao@eecs.berkeley.edu> (2015)

from xml.dom import minidom

def getTagData(node, tagName):
    return node.getElementsByTagName(tagName)[0].childNodes[0].data

def parse_xml(file_path):

    workloads_db = {} # workload_name -> workload
    benchmarks_db = []

    try:
        print "Parsing " + file_path
        xmldoc = minidom.parse(file_path)
        print "Getting workloads.."
        workloads = xmldoc.getElementsByTagName("workload")
        for workload in workloads:

            workload_dict = {}

            workload_name = getTagData(workload, "name")
            workload_dict['name'] = workload_name

            workload_description = getTagData(workload, "description")
            workload_dict['description'] = workload_description

            workload_path = getTagData(workload, "path")
            workload_dict['path'] = workload_path

            cl_options = []

            xml_cl_options = workload.getElementsByTagName("cl-options")[0]
            for child in xml_cl_options.childNodes:
                if child.nodeName == "#text":
                    continue
                else:
                    assert child.nodeName == "command"

                cmd_name = getTagData(child, "name")
                cmd_value = getTagData(child, "value")

                cl_options.append([cmd_name, cmd_value])

            workload_dict['cl-options'] = cl_options
            workloads_db[workload_dict['name']] = workload_dict
        
        print "Getting benchmarks.."
        benchmarks = xmldoc.getElementsByTagName("benchmark")
        for benchmark in benchmarks:
            benchmark_name = getTagData(benchmark, "name")
            benchmark_description = getTagData(benchmark, "description")
   
            # check if benchmark is sequential or concurrent
            seq = benchmark.getElementsByTagName("sequential")
            conc = benchmark.getElementsByTagName("concurrent")

            assert len(seq) == 0 or len(conc) == 0 # either sequential or concurrent

            workload_instances_list = []
            benchmark_mode = ""

            if len(seq) > 0:
                benchmark_mode = "sequential"
                for seq_workload in seq[0].childNodes:
                    if seq_workload.nodeName == "#text": # ??
                        continue
                    workload_instances_list += [seq_workload.getAttribute("name")]
            elif len(conc) > 0:
                benchmark_mode = "concurrent"
                for conc_workload in conc[0].childNodes:
                    if conc_workload.nodeName == "#text": # ??
                        continue
                    workload_instances_list += [conc_workload.getAttribute("name")]

            benchmarks_db += [{'name': benchmark_name,
                    'description': benchmark_description,
                    'mode': benchmark_mode,
                    'workloads': workload_instances_list}]

    except:
        print "Error parsing the configuration file " + file_path
        exit(-1)
    
    return [benchmarks_db, workloads_db]

import geni.portal as portal
import geni.rspec.pg as RSpec
import geni.rspec.igext
from lxml import etree as ET

pc = portal.Context()

pc.defineParameter( "n", "Number of Chef client nodes",
            portal.ParameterType.INTEGER, 1,
			longDescription="Please provide the number of Chef nodes you would like to instantiate and configure. One more client will run on the server node." )

pc.defineParameter( "raw", "Use physical Chef clients",
                    portal.ParameterType.BOOLEAN, True,
                    longDescription="Please check if you want to use physical machines. Otherwise, virtual machines are used. Chef server will still run on a physical machine." )

pc.defineParameter( "chefRepo", "Chef repository",
            portal.ParameterType.STRING, "https://github.com/emulab/chef-repo.git",
            longDescription="Please provide a URL for the Chef repository you intend to clone and use.")

pc.defineParameter( "communityCookbooks", "Cookbooks from Chef Supermarket",
            portal.ParameterType.STRING, "push-jobs nfs",
            longDescription="Please provide a space-separated list of community cookbooks you would like to download from Chef Supermarket: https://supermarket.chef.io/. These cookbooks and their dependencies will be installed into: /chef-repo/cookbooks")

pc.defineParameter( "defaultCookbooks", "Cookbooks applied to all clients",
            portal.ParameterType.STRING, "emulab-env",
            longDescription="Please provide a space-separated list of cookbooks you would like to run on all clients. These cookbooks will be assigned to clients but will not be executed - it is best to check node status and trigger configuration processes manually after the experiment is launched.")

pc.defineParameter( "defaultRoles", "Roles applied to all clients",
            portal.ParameterType.STRING, "push_client",
            longDescription="Please provide a space-separated list of roles you would like to apply on all clients. These roles will be assigned to clients but will not be executed - it is best to check node status and trigger configuration processes manually after the experiment is launched.")

pc.defineParameter( "serverName", "Name of the node with Chef server and workstation:",
            portal.ParameterType.STRING, "head", advanced=True,
            longDescription="Please provide a name you would like to use for the node, on which Chef server and workstation will be installed.")

pc.defineParameter( "clientPrefix", "Prefix in the names of Chef clients:",
            portal.ParameterType.STRING, "node", advanced=True,
            longDescription="Please provide the prefix you would like to use in the names of client machines. Their full names will have the format: \"<prefix>-<number>\".")

pc.defineParameter( "clientDaemonize", "Daemonize Chef clients",
                    portal.ParameterType.BOOLEAN, False, advanced=True,
                    longDescription="Please check if you want clients to periodically pull updated from the server. If checked, please set the following parameter appropriately. Otherwise, updates need to be triggered manually from the server (using knife utility)." )

pc.defineParameter( "daemonInterval", "Seconds between daemonized client runs",
                    portal.ParameterType.INTEGER, 30, advanced=True,
                    longDescription="Choose time (in seconds) between daemonized client runs. If the previous parameter is unchecked, this value is ignored." )

params = pc.bindParameters()

# Verify our parameters and throw errors.
if params.n < 0:
    perr = portal.ParameterError("Negative numer of clients? That does not work.",['n'])
    pc.reportWarning(perr)
    pass
if params.n > 8:
    perr = portal.ParameterWarning("Are you creating a real Chef system?  Otherwise, do you really need more than 8 compute nodes?  Think of your fellow users scrambling to get nodes :).",['n'])
    pc.reportWarning(perr)
    pass

IMAGE = "urn:publicid:IDN+emulab.net+image+emulab-ops:UBUNTU14-64-STD"

# Hostbased Auth: tarball and commands for server and clients
HBA_URL = "https://s3-us-west-2.amazonaws.com/dmdu-cloudlab/hba.tar.gz"
HBA_CMD_S = "sudo /bin/bash /root/hba-server-run.sh"
HBA_CMD_C = "sudo /bin/bash /root/hba-client-run.sh"

# Chef: tarball and command for server
CHEF_URL = "https://s3-us-west-2.amazonaws.com/dmdu-cloudlab/chef12-scripts-dev.tar.gz"
CHEF_CMD = "sudo /bin/bash /root/chef-run.sh"

class PublicVM(geni.rspec.igext.XenVM):
  def __init__ (self, name, component_id = None, exclusive = False):
    super(PublicVM, self).__init__(name)

  def _write (self, root):
    nd = super(PublicVM, self)._write(root)
    nd.attrib["{http://www.protogeni.net/resources/rspec/ext/emulab/1}routable_control_ip"] = str( "" )
    return nd


def Node( name, public ):
    if params.raw:
        return RSpec.RawPC( name )
    elif public:
        vm = PublicVM( name )
        return vm
    else:        
    	vm = geni.rspec.igext.XenVM( name )
        return vm

rspec = RSpec.Request()

node = Node( params.serverName, True )
node.disk_image = IMAGE
node.addService( RSpec.Install( HBA_URL, "/root" ) )
node.addService( RSpec.Execute( "sh", HBA_CMD_S ) )
node.addService( RSpec.Install( CHEF_URL, "/root" ) )
node.addService( RSpec.Execute( "sh", CHEF_CMD ) )
rspec.addResource( node )

if params.n > 0:  
  lan = RSpec.LAN()
  rspec.addResource( lan )
  iface = node.addInterface( "if0" )
  lan.addInterface( iface )
  for i in range( params.n ):
    node = Node( params.clientPrefix + "-" + str( i ), False )
    node.disk_image = IMAGE
    node.addService( RSpec.Install( HBA_URL, "/root" ) )
    node.addService( RSpec.Execute( "sh", HBA_CMD_C ) )
    iface = node.addInterface( "if0" )
    lan.addInterface( iface )
    rspec.addResource( node )

from lxml import etree as ET

tour = geni.rspec.igext.Tour()
tour.Description( geni.rspec.igext.Tour.TEXT, "This profile builds a Chef cluster with one Chef server, one Chef workstation, and multiple Chef clients." )

tourInstructions = \
"Approximately 5-10 minutes after your experiment is launched, you will recieve an email confirming that configuration is complete. \
\n\
\n\
After that, monitor your environment and manage your clients via the [Chef server WUI](http://{host-%s}). \
\n\
\n\
For detailed instructions, see the [full profile description](https://docs.google.com/document/d/1G3Hc-_DcebsueV3Lv989NvMDWPUzI6_RoLJjR6nymbs/edit?usp=sharing)." \
  % (params.serverName,)

tour.Instructions(geni.rspec.igext.Tour.MARKDOWN,tourInstructions)

rspec.addTour( tour )

#
# Add our parameters to the request so we can get their values to our nodes.
# The nodes download the manifest(s), and the setup scripts read the parameter
# values when they run.
#
class Parameters(RSpec.Resource):
    def _write(self, root):
        ns = "{http://www.protogeni.net/resources/rspec/ext/johnsond/1}"
        paramXML = "%sparameter" % (ns,)

        el = ET.SubElement(root,"%sprofile_parameters" % (ns,))

        param = ET.SubElement(el,paramXML)
        param.text = 'CHEFREPO="%s"' % (params.chefRepo,)
        param = ET.SubElement(el,paramXML)
        param.text = 'DEFAULTCOOKBOOKS="%s"' % (params.defaultCookbooks,)
        param = ET.SubElement(el,paramXML)
        param.text = 'DEFAULTROLES="%s"' % (params.defaultRoles,)
        param = ET.SubElement(el,paramXML)
        param.text = 'COMMUNITYCOOKBOOKS="%s"' % (params.communityCookbooks,)
        param = ET.SubElement(el,paramXML)
        param.text = 'CLIENTDAEMONIZE="%s"' % (params.clientDaemonize,)
        param = ET.SubElement(el,paramXML)
        param.text = 'DAEMONINTERVAL="%s"' % (params.daemonInterval,)
        param = ET.SubElement(el,paramXML)
        param.text = 'NCLIENTS="%s"' % (params.n,)
        
        return el
    pass

parameters = Parameters()
rspec.addResource(parameters)

pc.printRequestRSpec( rspec )

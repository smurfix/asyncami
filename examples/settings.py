#export AST_SERVER="fon.vm.smurf.noris.de:50080"
#export AST_ARI_PORT=50080
#export AST_AMI_PORT=5038
#export AST_USER=test
#export AST_PASS=test123
#export AST_APP=netz
#export AST_URL="http://fon.vm.smurf.noris.de:50080"
#export AST_OUTGOING="IAX2/smurf/tuer@ldispatch"

import os

connection = {
    'address': os.getenv("AST_SERVER",'127.0.0.1'),
    'port': int(os.getenv("AST_AMI_PORT",5038)),
}

login = {
    'username': os.getenv("AST_USER",'admin'),
    'secret': os.getenv("AST_PASS",'password'),
}

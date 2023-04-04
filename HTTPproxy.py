# Place your imports here
import signal, socket, threading
from optparse import OptionParser
import sys
from datetime import datetime
from urllib.parse import urlparse
# Signal handler for pressing ctrl-c
def ctrl_c_pressed(signal, frame):
	sys.exit(0)

# Start of program execution
# Parse out the command line server address and port number to listen to
parser = OptionParser()
parser.add_option('-p', type='int', dest='serverPort')
parser.add_option('-a', type='string', dest='serverAddress')
(options, args) = parser.parse_args()
# Set up signal handling (ctrl-c)
signal.signal(signal.SIGINT, ctrl_c_pressed)
 
port = options.serverPort
address = options.serverAddress
if address is None:
    address = 'localhost'
if port is None:
    port = 2100

#member variables
badReq = "HTTP/1.0 501 Not Implemented\r\nConnection: close\r\n\r\n"
badUrl = "HTTP/1.0 400 Bad Request\r\nConnection: close\r\n\r\n"
blckUrl = "HTTP/1.0 403 Forbidden\r\nConnection: close\r\n\r\n"
ok = "HTTP/1.0 200 OK\r\nConnection: close\r\n\r\n"
cache = {}  
blocked = []
blockOn = True
cacheOn= False

def checkHeaders(req):
    newlines = req.split("\r\n")
    returnArr = {}
    #split the request by new lines, go through each line and
    # check if it is a correctly formatted header
    for i in range(1,len(newlines),1):
        colon = newlines[i].split(": ")
        if(len(colon) == 2):
            #save the host and connection headers as to not duplicate them
            if(colon[0]) == "Host":
                returnArr['hostHeader'] = newlines[i]
            elif(colon[0] == "Connection"):
                if(colon[1] == "keep-alive"):
                    continue
                else:
                    returnArr['close'] = newlines[i]
            elif(colon[0][-1] != ' '):
                returnArr[i] = newlines[i]
            else:
                return badUrl
        elif newlines[i] == '':
            next
        else:
            return badUrl
    return returnArr

def addToCache(request,response):
    #todo
    now = datetime.now()
    day_name = now.strftime("%A")
    month_name = now.strftime("%B")
    date_time = "If-Modified-Since: "+day_name[0:3] +", " + now.strftime("%d ")+ month_name[0:3] + now.strftime("%Y %H:%M:%S GMT") 
    tuple = (response, date_time)
    cache[request] = tuple
        
def cached(Request):
    if Request in cache:
       return True
    else: 
        return False

def createGetReq(addr):
    new = "\r\n"
    close = "Connection: close"
    fullReq= "GET "
    host = [""] * 4

    if(cached(addr)):
        host[3]="True"
    else:
        host[3]="False"

    firstLine = addr.split("\r\n")[0].split(" ")

    url = urlparse(firstLine[1]) #the request should be properly formatted return bad req if not
    if url.path == '':
        return badUrl
    if url.scheme != "http":
        return badUrl
    if url.hostname is None:
        return badUrl
    
    if str(url.path).split("/")[1] == "proxy":
        return commandReq(str(url.path))
    
    else:
        headers = checkHeaders(addr) # check the headers for proper formatting
        if headers == badUrl:
            return badUrl
        
        host[0] = url.hostname
        if url.port is not None: #if the req has custom port format accordingly
            fullReq += url.path + " HTTP/1.0" +new  +"Host: " + url.hostname +":"+str(url.port) +new
            if host[3] == "True":
                fullReq += cache[addr][1]
            host[2] = url.port
            hostHeader = False
            closeHeader = False
            if len(headers) > 0:
                for i in headers:
                    if headers[i] == close:
                        closeHeader = True
                    fullReq += headers[i] +new
            else:
                fullReq += close + new
                closeHeader = True
            if closeHeader == False:
                fullReq += close + new

        else: #does not have a custom port 
            fullReq += url.path + " HTTP/1.0" +new 
            if host[3] == "True":
                fullReq += cache[addr][1] +new
            hostHeader = False
            closeHeader = False
            if len(headers) > 1:
                for i in headers:
                    fullReq += headers[i] +new
                    if i == "hostHeader":
                        hostHeader = True
                    elif i == 'close':
                        closeHeader = True
            if hostHeader and not closeHeader:
                fullReq += close +new
            elif closeHeader and not hostHeader:
                fullReq += "Host: " + url.hostname +new 
            else:
                fullReq += "Host: " + url.hostname +new + close +new
            host[2] = 80
    host[1] = fullReq + new
    return host

#returns True if the cached version is correct
def checkResponse(msg):
    try: 
        responseCode = msg.decode().split('\r\n')[0].split(' ')[1]
        if responseCode == "304":
            return True
        else:
            return False
    except:
        return False
    
    
def sendClientReq(req):
    connectTo = createGetReq(req)
    if connectTo == ok: #return ok if it was a proxy command
        return connectTo.encode()
    
    if connectTo != badReq and connectTo != badUrl:
        host = connectTo[0]
        sendReq = connectTo[1]
        port = connectTo[2]
        if blockOn and isBlocked(host+':'+str(port)):
            return blckUrl.encode()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if(connectTo[3] == "True" and cacheOn):
              #The Webpage is cached
               s.connect((host,port))
               s.sendall(sendReq.encode())
               receiveMessage = b""
               while True:
                   message = s.recv(4096)
                   if (len(message) > 0):
                        receiveMessage += message
                   else:
                       if checkResponse(receiveMessage): #returns true if cached version is correct
                           return cache[req][0]
                       addToCache(req,receiveMessage) #update the cache with new version
                       break
               s.close()
            else:
                #the webpage is not cached
                s.connect((host, port))
 
               #send http get request
                s.sendall(sendReq.encode())
                receiveMessage = b""
                while True:
                   message = s.recv(4096)
                   if (len(message) > 0):
                        receiveMessage += message 
                   else: 
                        if cacheOn:
                            addToCache(req,receiveMessage) #update the cache with new version
                        break 
                s.close()
        return receiveMessage
    else:
        return connectTo.encode()
    
#When your proxy receives a request containing one of the special absolute paths described below,
#it does not consult its cache or blocklist, nor does it forward the request to an origin server. Instead, it performs an operation on its cache or blocklist:
#/proxy/cache/enable
def commandReq(request):
    global blockOn
    global cacheOn

    formatReq = request.split("/")
    if len(formatReq) <= 1:
        return badReq
    if formatReq[2] == "cache":
        if formatReq[3] == "enable":
            cacheOn = True
            return ok
        elif formatReq[3] == "disable":
            cacheOn = False
            return ok
        elif formatReq[3] == "flush":
            cache.clear()
            return ok
    elif formatReq[2] == "blocklist":
        if formatReq[3] == "enable":
           blockOn = True
           return ok
        elif formatReq[3] == "disable":
           blockOn = False
           return ok
        elif formatReq[3] =="add":
           print(formatReq)
           sys.stdout.flush()
           blockStr = request.split("add/")[1].split("\r\n\r\n")[0]
           blocked.append(blockStr)
           return ok
        elif formatReq[3] =="remove":
             blockStr = request.split("remove/")[1].split("\r\n\r\n")[0]
             blocked.remove(blockStr)
             return ok
        elif formatReq[3]  == "flush":
            blocked.clear()
            return ok
    return badReq        
    
    
    
def isBlocked(addr):
    for host in blocked:
       if host in addr:
           return True
    return False    
           
           





#intial check of the users request verifing the proper format and how to process the request.
#i do not return a bool because when the request is bad i return a bad request as a string.
def checkReq(request):
    formatReq = request.split(" ")
    if(formatReq[0] == "GET" and len(formatReq) == 3 and formatReq[2][0:10] == "HTTP/1.0\r\n"):
        return "true"
    elif(len(formatReq) >3): # this case means the request has headers that need to be added.
       newlines= request.split("\r\n")
       if newlines[0].split(" ")[2] != "HTTP/1.0": #protocol is not 1.0 bad request
            return badUrl  
       return "true"
    elif(len(formatReq)== 3):
        if formatReq[0] != "GET": #only support GET reqs bad request
            return badReq
        elif formatReq[2] != "HTTP/1.0": #only suport HTTP 1.0
            return badUrl
    else:
        return badUrl
    
def connectClient(connection, returnAdd):
    with connection:
        print("connected to" + str(returnAdd))
         #recieve the client request
        message = connection.recv(2048)
        modifiedMessage = message.decode()
      
        while(len(modifiedMessage) > 4):
            if(modifiedMessage.endswith("\r\n\r\n")):
                break
            else:
                message = connection.recv(2048)
                modifiedMessage += message.decode()
                
        result = checkReq(modifiedMessage)
         #verify that the message is correct format  
        if(result == "true"):
                    #need to send through new socket
              recieveMsg= sendClientReq(modifiedMessage)
              connection.sendall(recieveMsg)               
        else:
            connection.sendall(result.encode())
            print(result)
            sys.stdout.flush()
#response = 'HTTP/1.1 200 OK\r\nDate: Sat, 25 Feb 2023 19:30:55 GMT\r\nServer: Apache/2.2.24 (FreeBSD) PHP/5.3.10 with Suhosin-Patch mod_ssl/2.2.24 OpenSSL/1.0.1h DAV/2\r\nLast-Modified: Sat, 22 Jan 2022 23:19:27 GMT\r\nETag: "206accd-c2-5d633f776fdc0"\r\nAccept-Ranges: bytes\r\nContent-Length: 194\r\nConnection: close\r\nContent-Type: text/html\r\n\r\n<!DOCTYPE html>\n<html lang="en">\n<head>\n  <meta charset="utf-8">\n  <title>Simple Page</title>\n</head>\n\n<body>\n<h1>Simple Page</h1>\n\n<p>\n  Hello!  This is simple HTML page.\n</p>\n</body>\n\n</html>\n'
def setUpServer():
    #using with to automatically close and clean up socket connection 
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as skt:
        skt.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        skt.bind((address,port))
        print("receiving on " + address + " "+ str(port)) 
        skt.listen() #start listening for incoming connections
        while True:
            connection, returnAdd = skt.accept() #found a connection creat another socket
            d= threading.Thread(name=str(returnAdd), target=connectClient, args=(connection, returnAdd))
            d.start()
        connection.close()
setUpServer()


      
        
         



from email.mime import image
import os, logging, pexpect, re, time, subprocess, sys
from versa_variables import *
port_number = 5
hostname = f"172.16.10{port_number}.1"
username = "admin"
password = "versa123"
prompt = "\$"


def versa_login():
    ch = pexpect.spawn(f'ssh {username}@{hostname}', timeout=30, maxread=65535)
    session_callback = ch.expect([pexpect.TIMEOUT, pexpect.EOF, 'yes/no', 'assword:', 'Connection refused', prompt] )
    if session_callback == 0:
        versa_terminate(ch, 'SSH timed out.' )
        return False
    elif session_callback == 1:
        versa_terminate(ch, 'SSH had an EOF error.' )
        return False
    elif session_callback == 2:
        send_and_expect(ch, 'yes', 'assword:')
        send_and_expect(ch, password, prompt)
        return True
    elif session_callback == 3:
        send_and_expect(ch, password, prompt)
        try:
            global versa_sn, versa_release, versa_details, versa_ls, versa_status, versa_interfaces
            versa_sn = versa_parse_output(ch, "vsh details", "Serial number")
            versa_release = versa_parse_output(ch, "vsh details", "Release")
            versa_details = send_and_expect(ch, 'vsh details', prompt)
            versa_ls = send_and_expect(ch, 'ls /home/versa/packages', prompt)
            send_and_expect(ch, 'vsh status', "admin:")
            versa_status = send_and_expect(ch, password, prompt)
            versa_interfaces = cli_send_and_expect(ch, 'show interfaces brief | tab | nomore')
            return True
        except:
            return False
    elif session_callback == 4:
        time.sleep(0.5)
        return False
    else:
        time.sleep(0.5)
        return False


def logging_function(port_number):
    global logger
    logger = logging.getLogger(f'port_{port_number}_logger')
    logger.setLevel(logging.DEBUG)
    level = logging.DEBUG
    fh = logging.FileHandler(f"/home/solar/versa_upgrade/log/port_{port_number}.log")
    fh.setLevel(logging.DEBUG)
    formatter = logging.Formatter('[%(levelname)s] [%(asctime)s]: %(message)s ')
    fh.setFormatter(formatter)
    fmt = '[%(levelname)s] [%(asctime)s]: %(message)s '
    logging.basicConfig(level=level, format=fmt)
    logger.addHandler(fh)    

def cli_send_and_expect(ch, send):
    send_and_expect(ch, "cli", "cli>")
    output = send_and_expect(ch, send, "cli>")
    send_and_expect(ch, "exit", prompt)
    return output

def versa_terminate(child, errstr):
    logger.error(errstr)
    logger.info(child.before)
    logger.info(child.after)
    child.terminate()


def versa_parse_output(ch, command, matching_string):
    output = send_and_expect(ch, command, prompt)
    variable_get = re.findall(r"[\n\r].*" + matching_string + "\s*([^\n\r\t]*)", output)
    try:
        return variable_get[0]
    except:
        return variable_get


def send_and_expect(ch, send, expect):
    ch.sendline(send)
    ch.expect([expect, pexpect.EOF, pexpect.TIMEOUT])
    output = ch.before.decode()
    return output


def versa_ping(response=None):
    while response != 0:
        response = os.system("ping -c 1 " + hostname)
    else:
        return True


def versa_upgrade():
    try:
        ch = pexpect.spawn(f'ssh {username}@{hostname}', timeout=30, maxread=65535)
        ch.logfile = sys.stdout.buffer
        ch.expect(['assword:', pexpect.EOF, pexpect.TIMEOUT])
        send_and_expect(ch, password, prompt)
        send_and_expect(ch, "cli", "cli>")
        send_and_expect(ch, f"request system package upgrade {image_filename}", "[no,yes]")
        send_and_expect(ch, "yes", "cli>")
        return True
    except:
        return False

def versa_upload():
    try:
        cmd = f'sshpass -p {password} scp -o StrictHostKeyChecking=no /home/solar/versa_upgrade/{image_filename} {username}@{hostname}:/home/versa/packages/'
        output = subprocess.check_output(cmd, shell=True)
        logger.info(output)
        return True
    except:
        return False

def versa_hosts_file():
    try:
        os.remove(hosts_path)
    except:
        logging.info(f"No file in {hosts_path} to remove")

def versa_shutdown():
    try:
        ch = pexpect.spawn(f'ssh {username}@{hostname}', timeout=30, maxread=65535)
        ch.logfile = sys.stdout.buffer
        ch.expect(['assword:', pexpect.EOF, pexpect.TIMEOUT])
        send_and_expect(ch, password, prompt)
        send_and_expect(ch, "cli", "cli>")
        send_and_expect(ch, f"request system shutdown", "[no,yes]")
        shutdown_log = send_and_expect(ch, "yes", "cli>")
        logger.error(shutdown_log)
        return True
    except:
        return False


def main():
    logging_function(port_number)

    
    try:
        while True:

            if not versa_ping():
                logger.info("Ping check failed")
            else:
                logger.info("Ping: Successful")
                if not versa_login():
                    logger.info("Login failed, will try again in 30 seconds.")
                    versa_hosts_file()
                    time.sleep(30)
                else:
                    logger.info("Login: Successful")
                    try: 
                        if "Stopped" in versa_status:
                            logger.info("Some services have stopped, will try again in 2 minutes.")
                            time.sleep(120)
                        elif "Running" in versa_status:
                            logger.info("All services are running")
                            if versa_release in image_filename:
                                logger.info(f"SERIAL NUMBER: {versa_sn}")
                                logger.info(f"{versa_sn} has the right version: {versa_release}")
                                time.sleep(30)
                                if "WAN1-Transport-VR" in versa_interfaces:
                                    logger.info(f"Device has WAN interface in correct VRF.")
                                    logger.info(f"Will stop script for 1 minutes, then shutdown device.")
                                    time.sleep(60)
                                    if not versa_shutdown():
                                        logger.error(f"Unable to shutdown device, will wait 1 minutes.")
                                        time.sleep(60)
                                    else:
                                        logger.info(f"COMPLETED {versa_sn} COMPLETED")
                                        logger.info(f"Device is shutting down, will wait 2 minutes.")
                                        with open(f"/home/solar/versa_upgrade/completed_devices/{versa_sn}.log", "w") as f:
                                            f.write(f"Start of file\n {versa_sn} \n {versa_details} \n {versa_status} \n {versa_interfaces}\n end of file\n")
                                            logger.info(f"Created file: completed_devices/{versa_sn}.log")
                                        time.sleep(120)
                                else:
                                    logger.info(f"Device does not have WAN interface in correct VRF.")
                                    time.sleep(10)
                            else:
                                logger.info(f"{versa_sn} has the wrong version: {versa_release}")
                                if image_filename in versa_ls:
                                    logger.info(f"{versa_sn} has {image_filename} in /home/versa/packages")
                                    if not versa_upgrade():
                                        logger.info(f"{versa_sn} Failed to upgrade device with {image_filename}.")
                                        time.sleep(30)
                                    else:
                                        logger.info(f"{versa_sn} Successfully started upgrade of device with {image_filename}.")
                                        logger.info(f"{versa_sn} Waiting 5 minutes for the device to complete upgrade.")
                                        time.sleep(300)
                                else:
                                    logger.info(f"{versa_sn} is missing {image_filename}, starting upload")
                                    if not versa_upload():
                                        logger.info(f"{versa_sn} Failed to upload {image_filename} to /home/versa/packages")
                                        time.sleep(30)
                                    else:
                                        logger.info(f"{versa_sn} Successfully uploaded {image_filename} to /home/versa/packages")
                                        time.sleep(10)
                                        if not versa_upgrade():
                                            logger.info(f"{versa_sn} Failed to upgrade device with {image_filename}.")
                                            time.sleep(10)
                                        else:
                                            logger.info(f"{versa_sn} Successfully started upgrade of device with {image_filename}.")
                                            logger.info(f"{versa_sn} Waiting 5 minutes for the device to complete upgrade.")
                                            time.sleep(300)
                        else:
                            logger.info("Status is not stopped or running")  
                            time.sleep(10) 

                    except:
                        logger.info("Lost connection when getting variables")
                        time.sleep(10)
    except KeyboardInterrupt:
        logger.warning(f"Session has been stopped with Ctrl+C.")
if __name__ == '__main__':
    main()







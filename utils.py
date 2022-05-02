import sys
import logging
import subprocess

logging.basicConfig(level=logging.INFO,
        format='[%(asctime)s %(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S')

logger = logging.getLogger()

def check_output_and_logging(*popenargs, **kwargs):
    process = subprocess.Popen(*popenargs, stdout=subprocess.PIPE, **kwargs)
    logger.info(str(popenargs))
    output = b''
    for line in iter(process.stdout.readline, b''):
        logger.info(line.decode().replace('\n', ''))
        output += line
    process.stdout.close()

    retcode = process.wait()
    if retcode != 0:
        raise subprocess.CalledProcessError(retcode, process.args, output=output)

    return output


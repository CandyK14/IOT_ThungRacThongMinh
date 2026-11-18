"""CA local chỉ dành cho lab. Không tự cài vào trust store của Windows."""
import argparse
import ipaddress
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID


def create(directory,host='localhost'):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    if any((directory/name).exists() for name in ('ca.key','ca.crt','server.key','server.crt')):
        raise ValueError('Không ghi đè CA/certificate đã có. Chọn thư mục mới.')
    now=datetime.now(timezone.utc)
    ca_key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    ca_name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'SmartBin Local Lab CA')])
    ca=(x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name).public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=5)).not_valid_after(now+timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True,path_length=0),critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True,key_encipherment=False,key_cert_sign=True,crl_sign=True,content_commitment=False,data_encipherment=False,key_agreement=False,encipher_only=False,decipher_only=False),critical=True)
        .sign(ca_key,hashes.SHA256()))
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    names=[x509.DNSName('localhost'),x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]
    try:names.append(x509.IPAddress(ipaddress.ip_address(host)))
    except ValueError:names.append(x509.DNSName(host))
    cert=(x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,host)]))
          .issuer_name(ca_name).public_key(key.public_key()).serial_number(x509.random_serial_number())
          .not_valid_before(now-timedelta(minutes=5)).not_valid_after(now+timedelta(days=90))
          .add_extension(x509.SubjectAlternativeName(names),critical=False)
          .add_extension(x509.BasicConstraints(ca=False,path_length=None),critical=True)
          .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),critical=False).sign(ca_key,hashes.SHA256()))
    for filename,value in [('ca.crt',ca.public_bytes(serialization.Encoding.PEM)),('server.crt',cert.public_bytes(serialization.Encoding.PEM)),
                           ('ca.key',ca_key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())),
                           ('server.key',key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))]:
        with (directory/filename).open('xb') as f:f.write(value)
    return directory


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--host',default='localhost');p.add_argument('--output',default='broker/certs')
    args=p.parse_args();print(create(args.output,args.host))

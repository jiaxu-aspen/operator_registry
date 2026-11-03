"""Read a contactless card UID through Windows PC/SC, without writing card data."""
import ctypes as c
from ctypes import wintypes as w

class CardError(RuntimeError):
    pass

class Reader:
    """Own one PC/SC context. Handles are pointer-sized on 64-bit Windows."""
    def __init__(self):
        self.dll=c.WinDLL('winscard.dll'); self.context=c.c_size_t()
        H=c.c_size_t; D=w.DWORD; P=c.POINTER
        signatures={
            'SCardEstablishContext':([D,c.c_void_p,c.c_void_p,P(H)],w.LONG),
            'SCardReleaseContext':([H],w.LONG),
            'SCardListReadersW':([H,w.LPCWSTR,w.LPWSTR,P(D)],w.LONG),
            'SCardConnectW':([H,w.LPCWSTR,D,D,P(H),P(D)],w.LONG),
            'SCardDisconnect':([H,D],w.LONG),
            'SCardTransmit':([H,c.c_void_p,c.c_void_p,D,c.c_void_p,c.c_void_p,P(D)],w.LONG),
        }
        for name,(args,result) in signatures.items():
            f=getattr(self.dll,name);f.argtypes=args;f.restype=result
        self.check(self.dll.SCardEstablishContext(0,None,None,c.byref(self.context)))

    @staticmethod
    def check(code):
        """Translate common PC/SC failures into operator-readable messages."""
        code=code & 0xffffffff
        if code:
            descriptions={0x8010000C:'No card detected. Hold one card on the reader and scan again.',
              0x80100069:'Card removed. Hold it steady and scan again.',
              0x8010000B:'Reader is in use by another application. Close it and retry.',
              0x80100017:'Reader unavailable. Check the USB connection.',
              0x8010001D:'Windows Smart Card service is not running.',
              0x8010002E:'No smart-card readers found. Check the USB connection.'}
            raise CardError(descriptions.get(code,f'PC/SC error 0x{code:08X}.'))

    def readers(self):
        """Windows returns a double-null-terminated list of reader names."""
        n=w.DWORD()
        self.check(self.dll.SCardListReadersW(self.context,None,None,c.byref(n)))
        buf=c.create_unicode_buffer(n.value)
        self.check(self.dll.SCardListReadersW(self.context,None,buf,c.byref(n)))
        return [x for x in buf[:n.value].split('\0') if x and 'OMNIKEY' in x.upper()]

    def uid(self,name):
        """GET DATA FF CA 00 00 00 reads the UID; 9000 denotes success.

        UID is an identification aid, not proof of identity. Some credentials
        randomize their UID or do not expose one; no credential keys are read.
        """
        card=c.c_size_t(); protocol=w.DWORD()
        self.check(self.dll.SCardConnectW(self.context,name,2,3,c.byref(card),c.byref(protocol)))
        try:
            class PCI(c.Structure):
                _fields_=[('protocol',w.DWORD),('length',w.DWORD)]
            pci=PCI(protocol.value,c.sizeof(PCI))
            request=(c.c_ubyte*5)(0xff,0xca,0,0,0)
            response=(c.c_ubyte*258)(); n=w.DWORD(258)
            self.check(self.dll.SCardTransmit(card,c.byref(pci),request,5,None,response,c.byref(n)))
            raw=bytes(response[:n.value])
            if len(raw)<3 or raw[-2:]!=b'\x90\x00':
                raise CardError('This card did not return a supported UID (response '+raw.hex(' ').upper()+').')
            return raw[:-2].hex().upper()
        finally:
            self.dll.SCardDisconnect(card,0) # LEAVE_CARD: do not reset or power down the credential.

    def close(self):
        if self.context.value:
            self.dll.SCardReleaseContext(self.context);self.context=c.c_size_t()

from collections.abc import Iterator

class tinfo_t:
    def dstr(self) -> str: ...
    def get_func_details(self, details: func_type_data_t) -> bool: ...

class funcarg_t:
    name: str
    type: tinfo_t

class func_type_data_t:
    rettype: tinfo_t

    def __iter__(self) -> Iterator[funcarg_t]: ...

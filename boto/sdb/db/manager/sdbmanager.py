# Copyright (c) 2006,2007,2008 Mitch Garnaat http://garnaat.org/
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish, dis-
# tribute, sublicense, and/or sell copies of the Software, and to permit
# persons to whom the Software is furnished to do so, subject to the fol-
# lowing conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
# OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABIL-
# ITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT
# SHALL THE AUTHOR BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, 
# WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.
import boto
from boto.utils import find_class
import datetime
from boto.sdb.db.key import Key

def object_lister(cls, query_lister, manager):
    for item in query_lister:
        if cls:
            yield cls(item.name)
        else:
            o = manager.get_object_from_id(item.name)
            if o:
                yield o
                
ISO8601 = '%Y-%m-%dT%H:%M:%SZ'

class Converter:
    
    """
    Responsible for converting base Python types to format compatible with underlying
    database.  For SimpleDB, that means everything needs to be converted to a string
    when stored in SimpleDB and from a string when retrieved.

    To convert a value, pass it to the encode or decode method.  The encode method
    will take a Python native value and convert to DB format.  The decode method will
    take a DB format value and convert it to Python native format.  To find the appropriate
    method to call, the generic encode/decode methods will look for the type-specific
    method by searching for a method called "encode_<type name>" or "decode_<type name>".
    """

    @classmethod
    def encode(cls, manager, prop, value):
        if hasattr(prop, 'reference_class'):
            return cls.encode_reference(manager, value)
        if isinstance(value, str) or isinstance(value, unicode):
            return value
        if isinstance(value, int) or isinstance(value, long):
            return cls.encode_int(manager, value)
        if isinstance(value, bool):
            return cls.encode_bool(manager, value)
        if isinstance(value, datetime.datetime):
            return cls.encode_datetime(manager, value)

    @classmethod
    def decode(cls, manager, prop, value):
        if isinstance(prop.data_type, str) or isinstance(prop.data_type, unicode):
            return value
        if isinstance(prop.data_type, int) or isinstance(prop.data_type, long):
            return cls.decode_int(manager, value)
        if isinstance(prop.data_type, bool):
            return cls.decode_bool(manager, value)
        if isinstance(prop.data_type, datetime.datetime):
            return cls.decode_datetime(manager, value)
        if isinstance(prop.data_type, Key):
            return cls.decode_reference(manager, value)
        

    @classmethod
    def encode_int(cls, manager, value):
        value = long(value)
        value += 9223372036854775808
        return '%020d' % value

    @classmethod
    def decode_int(cls, manager, value):
        value = long(value)
        value -= 9223372036854775808
        return value

    @classmethod
    def encode_bool(cls, manager, value):
        if value == True:
            return 'true'
        else:
            return 'false'
    
    @classmethod
    def decode_bool(cls, manager, value):
        if value.lower() == 'true':
            return True
        else:
            return False
        
    @classmethod
    def encode_datetime(cls, manager, value):
        return value.strftime(ISO8601)
    
    @classmethod
    def decode_datetime(cls, manager, value):
        try:
            return datetime.strptime(value, ISO8601)
        except:
            raise ValueError, 'Unable to convert %s to DateTime' % str_value

    @classmethod
    def encode_reference(cls, manager, value):
        if isinstance(value, str) or isinstance(value, unicode):
            return value
        if value == None:
            return ''
        else:
            return value.id
    
    @classmethod
    def decode_reference(cls, manager, value):
        if not value:
            return None
        try:
            return manager.get_object_from_id(value)
        except:
            raise ValueError, 'Unable to convert %s to Object' % str_value
    
class SDBManager(object):

    DefaultDomainName = boto.config.get('Persist', 'default_domain', None)

    def __init__(self, domain_name=None, aws_access_key_id=None, aws_secret_access_key=None, debug=0):
        self.domain_name = domain_name
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key
        self.domain = None
        self.sdb = None
        self.s3 = None
        if not self.domain_name:
            self.domain_name = self.DefaultDomainName
            if self.domain_name:
                boto.log.info('No SimpleDB domain set, using default_domain: %s' % self.domain_name)
            else:
                boto.log.warning('No SimpleDB domain set, persistance is disabled')
        if self.domain_name:
            self.sdb = boto.connect_sdb(aws_access_key_id=self.aws_access_key_id,
                                        aws_secret_access_key=self.aws_secret_access_key,
                                        debug=debug)
            self.domain = self.sdb.lookup(self.domain_name)
            if not self.domain:
                self.domain = self.sdb.create_domain(self.domain_name)

    def get_s3_connection(self):
        if not self.s3:
            self.s3 = boto.connect_s3(self.aws_access_key_id, self.aws_secret_access_key)
        return self.s3

    def get_object(self, cls, id):
        a = self.domain.get_attributes(id, '__type__')
        if a.has_key('__type__'):
            return cls(id)
        else:
            raise SDBPersistenceError('%s object with id=%s does not exist' % (cls.__name__, id))
        
    def get_object_from_id(self, id):
        attrs = self.domain.get_attributes(id, ['__module__', '__type__', '__lineage__'])
        try:
            cls = find_class(attrs['__module__'], attrs['__type__'])
            return cls(id, manager=self)
        except ImportError:
            return None

    def query(self, cls, filters):
        if len(filters) > 4:
            raise SDBPersistenceError('Too many filters, max is 4')
        parts = ["['__type__'='%s'] union ['__lineage__'starts-with'%s']" % (cls.__name__, cls.get_lineage())]
        properties = cls.properties()
        for filter in filters:
            name, op = filter.strip().split()
            found = False
            for property in properties:
                if property.name == key:
                    found = True
                    if isinstance(property, ScalarProperty):
                        checker = property.checker
                        parts.append("['%s' %s '%s']" % (name, op, checker.to_string(params[key])))
                    else:
                        raise SDBPersistenceError('%s is not a searchable field' % key)
            if not found:
                raise SDBPersistenceError('%s is not a valid field' % key)
        query = ' intersection '.join(parts)
        rs = self.domain.query(query)
        return object_lister(cls, rs, self)

    def save_object(self, obj):
        attrs = {'__type__' : obj.__class__.__name__,
                 '__module__' : obj.__class__.__module__,
                 '__lineage__' : obj.get_lineage()}
        for property in obj.properties():
            attrs[property.name] = property.get_value_for_datastore(obj)
        self.domain.put_attributes(obj.id, attrs, replace=True)

    def delete_object(self, obj):
        self.domain.delete_attributes(obj.id)

    def get_related_objects(self, obj, relation_name, relation_cls):
        query = "['%s' = '%s']" % (relation_name, obj.id)
        if relation_cls:
            query += " intersection ['__type__'='%s']" % relation_cls.__name__
        rs = self.domain.query(query)
        return object_lister(relation_cls, rs, self)

    def encode_value(self, prop, value):
        return Converter.encode(self, prop, value)

    def set_property(self, prop, obj, name, value):
        value = self.encode_value(self, prop, value)
        self.domain.put_attributes(obj.id, {name : value}, replace=True)

    def decode_value(self, prop, value):
        return Converter.decode(self, prop, value)

    def get_property(self, prop, obj, name):
        a = self.domain.get_attributes(obj.id, name)
        # try to get the attribute value from SDB
        if name in a:
            return self.decode_value(prop, a[name])
        raise AttributeError, '%s not found' % name

    def set_key_value(self, obj, name, value):
        self.domain.put_attributes(obj.id, {name : value}, replace=True)

    def get_key_value(self, obj, name):
        a = self.domain.get_attributes(obj.id, name)
        if a.has_key(name):
            return a[name]
        else:
            return None
    
    def get_raw_item(self, obj):
        return self.domain.get_item(obj.id)
        

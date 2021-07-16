from nle import nethack as nh

obj_classes = {getattr(nh, x): x for x in dir(nh) if x.endswith('_CLASS')}
glyph_classes = sorted((getattr(nh, x), x) 
                       for x in dir(nh) if x.endswith('_OFF'))
offset=0
for i in range(nh.MAX_GLYPH):
    desc = ''
    if glyph_classes and i == glyph_classes[0][0]:
        offset = i
        cls = glyph_classes.pop(0)[1]
    
    if nh.glyph_is_monster(i):
        desc = f': "{nh.permonst(nh.glyph_to_mon(i)).mname}"'
    
    if nh.glyph_is_normal_object(i):
        obj = nh.objclass(nh.glyph_to_obj(i))
        appearance = nh.OBJ_DESCR(obj) or nh.OBJ_NAME(obj) 
        oclass = ord(obj.oc_class)
        desc = f': {obj_classes[oclass]}: "{appearance}"'

    print(f'Glyph {i} Glyph off {i-offset} Type: {cls.replace("_OFF","")} {desc}'  )
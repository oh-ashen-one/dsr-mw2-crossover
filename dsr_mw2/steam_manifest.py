"""Build DSR install registration using game metadata only, never account state."""
import re


def parse(text):
    if len(text)>1024*1024:raise ValueError('Oversized game manifest')
    tokens=re.findall(r'"(?:\\.|[^"\\])*"|[{}]',text)
    i=0
    def block(nested=False):
        nonlocal i
        result={}
        while i<len(tokens):
            key=tokens[i];i+=1
            if key=='}':
                if not nested:raise ValueError('Unexpected manifest close')
                return result
            if not key.startswith('"') or i>=len(tokens):raise ValueError('Malformed manifest key')
            key=key[1:-1]
            if key in result:raise ValueError('Duplicate manifest key')
            value=tokens[i];i+=1
            if value=='{':value=block(True)
            elif value.startswith('"'):value=value[1:-1]
            else:raise ValueError('Malformed manifest value')
            result[key]=value
        if nested:raise ValueError('Unclosed manifest section')
        return result
    return block()


def installed_dsr_manifest(source):
    state=parse(source).get('AppState',{})
    if state.get('appid')!='570940' or state.get('StateFlags')!='4':
        raise ValueError('Source DSR install is not complete')
    if state.get('Universe') != '1':raise ValueError('Expected the public Steam universe')
    out={'appid':'570940','Universe':'1','name':'DARK SOULS REMASTERED','StateFlags':'4','installdir':'DARK SOULS REMASTERED'}
    for key in ('buildid','SizeOnDisk','LastUpdated'):
        value=state.get(key)
        if not isinstance(value,str) or not value.isdigit():raise ValueError('Missing game metadata: '+key)
        out[key]=value
    depots=state.get('InstalledDepots')
    if not isinstance(depots,dict) or not depots:raise ValueError('Installed depot metadata is missing')
    out['InstalledDepots']={}
    for depot,values in depots.items():
        if not depot.isdigit() or not isinstance(values,dict):raise ValueError('Invalid depot record')
        out['InstalledDepots'][depot]={}
        for key in ('manifest','size'):
            value=values.get(key)
            if not isinstance(value,str) or not value.isdigit():raise ValueError('Incomplete depot record')
            out['InstalledDepots'][depot][key]=value
    # Only this game's public install language is selected; LastOwner,
    # credentials, login/account fields and all unknown fields are excluded.
    language=state.get('UserConfig',{}).get('language','english')
    if not isinstance(language,str) or not re.fullmatch('[a-z_-]{2,30}',language):raise ValueError('Invalid install language')
    out['UserConfig']={'language':language}
    def render(values,depth=0):
        lines=[];tab='\t'*depth
        for key,value in values.items():
            if isinstance(value,dict):lines.extend([tab+'"'+key+'"',tab+'{',render(value,depth+1),tab+'}'])
            else:lines.append(tab+'"'+key+'"\t"'+value+'"')
        return '\n'.join(lines)
    return render({'AppState':out})+'\n'

"""Offline two-bone rotation solver; never changes local translations or scale."""
import math
from .animation_pose import Transform, inverse, multiply, unit
from .skin_geometry import world_transforms


def sub(a,b):return tuple(x-y for x,y in zip(a,b,strict=True))
def add(a,b):return tuple(x+y for x,y in zip(a,b,strict=True))
def mul(a,b):return tuple(x*b for x in a)
def dot(a,b):return sum(x*y for x,y in zip(a,b,strict=True))
def length(a):return math.sqrt(dot(a,a))
def normalized(a):
    n=length(a)
    if n<1e-10:raise ValueError('Degenerate IK vector')
    return mul(a,1/n)
def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])


def swing(before,after):
    a,b=normalized(before),normalized(after);d=max(-1.,min(1.,dot(a,b)))
    if d<-1+1e-9:
        axis=normalized(cross(a,(1.,0.,0.) if abs(a[0])<.8 else (0.,1.,0.)))
        return (*axis,0.)
    return unit((*cross(a,b),1+d))


def set_world_rotation(pose,parents,bone,rotation):
    world=world_transforms(parents,pose)
    local=rotation if parents[bone]<0 else multiply(inverse(world[parents[bone]].rotation),rotation)
    result=list(pose);result[bone]=Transform(local,pose[bone].translation)
    return result


def aim_child(pose,parents,bone,child,direction):
    if parents[child]!=bone:raise ValueError('IK child must be direct')
    world=world_transforms(parents,pose)
    q=swing(sub(world[child].translation,world[bone].translation),direction)
    return set_world_rotation(pose,parents,bone,multiply(q,world[bone].rotation))


def two_bone(pose,parents,upper,elbow,hand,target,pole,hand_rotation):
    if parents[elbow]!=upper or parents[hand]!=elbow:raise ValueError('IK chain differs')
    if not all(math.isfinite(x) for v in (target,pole) for x in v):raise ValueError('Nonfinite IK target')
    world=world_transforms(parents,pose);start=world[upper].translation
    a=length(sub(world[elbow].translation,start));b=length(sub(world[hand].translation,world[elbow].translation))
    wanted=sub(target,start);d=length(wanted);direction=normalized(wanted)
    reach=max(abs(a-b)+1e-5,min(a+b-1e-5,d))
    target=add(start,mul(direction,reach))
    toward=sub(pole,start);orthogonal=normalized(sub(toward,mul(direction,dot(toward,direction))))
    along=(a*a-b*b+reach*reach)/(2*reach)
    height=math.sqrt(max(0.,a*a-along*along))
    bend=add(add(start,mul(direction,along)),mul(orthogonal,height))
    result=aim_child(pose,parents,upper,elbow,sub(bend,start))
    world=world_transforms(parents,result)
    result=aim_child(result,parents,elbow,hand,sub(target,world[elbow].translation))
    result=set_world_rotation(result,parents,hand,hand_rotation)
    final=world_transforms(parents,result)
    error=math.dist(final[hand].translation,target)
    if error>1e-6:raise ValueError('Two-bone solve failed: '+str(error))
    if any(a.translation!=b.translation for a,b in zip(pose,result,strict=True)):raise ValueError('Bone length changed')
    return result,{'target_clamp_m':abs(reach-d),'endpoint_error_m':error,'hand_m':final[hand].translation}

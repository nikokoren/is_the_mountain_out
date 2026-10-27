"""Fixed observers keep weather geometry and artwork in agreement."""
from math import asin, cos, radians, sin, sqrt

PARADISE = dict(id='paradise', name='Paradise', latitude=46.786, longitude=-121.735,
                image_path='/assets/rainier.png')
SEATTLE = dict(id='seattle', name='Seattle — Kerry Park', latitude=47.6295,
               longitude=-122.3599, image_path='/assets/rainier-seattle.png')
TACOMA = dict(id='tacoma', name='Tacoma — Jack Hyde Park / Ruston Way',
              latitude=47.2809, longitude=-122.4608,
              image_path='/assets/rainier-tacoma.png')
PORTLAND = dict(id='portland', name='Portland — Pittock Mansion',
                latitude=45.5252, longitude=-122.7163,
                image_path='/assets/hood-portland.png', mountain='hood')
for viewpoint in (SEATTLE, PARADISE, TACOMA):
    viewpoint['mountain'] = 'rainier'
VIEWPOINTS = {'seattle': SEATTLE, 'paradise': PARADISE, 'tacoma': TACOMA, 'portland': PORTLAND}
MOUNTAINS = {'rainier': dict(name='Mount Rainier / Tahoma', summit=(46.8523, -121.7603)),
             'hood': dict(name='Mount Hood / Wy’east', summit=(45.3736, -121.6959))}
SUMMIT = (46.8523, -121.7603)


def distance(a, b):
    lat1, lat2 = radians(a[0]), radians(b[0])
    dlat, dlon = lat2 - lat1, radians(b[1] - a[1])
    return 6371000 * 2 * asin(sqrt(sin(dlat / 2)**2 + cos(lat1)*cos(lat2)*sin(dlon / 2)**2))


def samples(location):
    origin = (location['latitude'], location['longitude'])
    if location['id'] == 'paradise':
        return [origin]
    summit = MOUNTAINS[location.get('mountain', 'rainier')]['summit']
    # Four points on the approximate viewing corridor. No terrain/height inference.
    return [(origin[0] + (summit[0] - origin[0])*f,
             origin[1] + (summit[1] - origin[1])*f) for f in (0, 1/3, 2/3, 1)]

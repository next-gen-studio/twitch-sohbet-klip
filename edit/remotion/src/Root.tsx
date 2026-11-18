import React from 'react';
import {Composition} from 'remotion';
import {Short, ShortProps} from './Short';

const ornek: ShortProps = {
  sure: 5, kaynak: 'ham', baslik: 'WAIT FOR IT', baslikEmoji: '😳', yayinci: '',
  altyazi: [], emojiler: [], zoomlar: [], sfx: [],
};

export const RemotionRoot: React.FC = () => (
  <Composition
    id="Short"
    component={Short}
    width={1080}
    height={1920}
    fps={30}
    durationInFrames={150}
    defaultProps={ornek}
    calculateMetadata={({props}) => ({durationInFrames: Math.max(30, Math.round(props.sure * 30))})}
  />
);

import { Composition } from 'remotion';
import { LemminoExperience } from './LemminoExperience';

export const Root = () => {
  return (
    <>
      <Composition
        id="LemminoExperience"
        component={LemminoExperience}
        durationInFrames={1500} // 50 ثانية كاملة
        fps={30}
        width={1920}
        height={1080}
      />
    </>
  );
};

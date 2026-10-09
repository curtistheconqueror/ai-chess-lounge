import { useState } from "react";
import { BoardSoundControls, useBoardSound } from "./BoardSoundControls";
import { woodSamples } from "./boardSound";

export function SoundLab() {
  const sound = useBoardSound();
  const [last, setLast] = useState<number | null>(null);
  return <main className="sound-lab app-shell">
    <header className="sound-lab-heading">
      <div><p className="eyebrow">AI CHESS LOUNGE · AUDIO STUDIO</p>
        <h1>Find your wooden sound.</h1>
        <p>Twelve original piece-on-board candidates. Tap, compare, then tell us your number.</p>
      </div>
      <a className="ghost-button" href="/">Back to the board</a>
    </header>
    <BoardSoundControls sound={sound} />
    <p className="sound-lab-note">Sound 1 is the current board sound. Auditioning leaves your game sound unchanged.
      Each replay stops the previous sample. Nothing plays automatically.</p>
    <section className="sound-grid" aria-label="Wooden sound samples">
      {woodSamples.map(sample => <article className={`sound-card ${last === sample.id ? "auditioned" : ""}`} key={sample.id}>
        <div className="sound-card-top"><span className="eyebrow">SOUND {sample.id}</span>
          {sample.id === 1 && <span className="sound-default">BOARD DEFAULT</span>}</div>
        <h2>{sample.name}</h2><p>{sample.description}</p>
        <div className="wood-rings" aria-hidden="true"><i /><i /><i /></div>
        <button className="ghost-button" aria-label={`Replay Sound ${sample.id}`}
          disabled={sound.settings.muted || sound.settings.volume === 0}
          onClick={() => { setLast(sample.id); void sound.testSound(sample.id); }}>▶ Replay Sound {sample.id}</button>
      </article>)}
    </section>
    <p className="sound-lab-note" aria-live="polite">{last === null ? "Choose any sample to begin."
      : `Last requested: Sound ${last}. Try it again or compare another number.`}</p>
    <p className="sound-lab-note">Original synthesized contacts; no recordings copied from another chess app.
      Device speakers and volume affect what you hear.</p>
  </main>;
}

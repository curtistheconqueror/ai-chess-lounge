import { useState } from "react";
import { BoardSoundControls, useBoardSound } from "./BoardSoundControls";
import { auditionSamples, denseSamples, originalPrototype, woodSamples } from "./boardSound";

export function SoundLab() {
  const sound = useBoardSound(true);
  const [last, setLast] = useState<number | null>(null);
  const card = (sample: (typeof auditionSamples)[number]) => <article
    className={`sound-card ${last === sample.id ? "auditioned" : ""}`} key={sample.id}>
    <div className="sound-card-top"><span className="eyebrow">SOUND {sample.id}</span>
      {sample.id === originalPrototype.id && <span className="sound-default">SELECTED · ORIGINAL WAV</span>}
      {sample.id >= 14 && <span className="sound-default">NEW · DENSE</span>}</div>
    <h2>{sample.name}</h2><p>{sample.description}</p>
    <div className="wood-rings" aria-hidden="true"><i /><i /><i /></div>
    <button className="ghost-button" aria-label={`Replay Sound ${sample.id}`}
      disabled={sound.settings.muted || sound.settings.volume === 0}
      onClick={() => { setLast(sample.id); void sound.testSound(sample.id); }}>▶ Replay Sound {sample.id}</button>
  </article>;
  return <main className="sound-lab app-shell">
    <header className="sound-lab-heading">
      <div><p className="eyebrow">AI CHESS LOUNGE · AUDIO STUDIO</p>
        <h1>Find your wooden sound.</h1>
        <p>The original prototype is selected. Earlier and dense candidates remain here for later comparison.</p>
      </div>
      <a className="ghost-button" href="/">Back to the board</a>
    </header>
    <BoardSoundControls sound={sound} />
    <p className="sound-lab-note">Sound 13 is the selected board sound. Auditioning leaves your game sound unchanged.
      Each replay stops the previous sample. Nothing plays automatically.
      Sound 13 is the supplied original single-tap prototype, kept at its original level.</p>
    <nav className="sound-comparison-links" aria-label="Sound comparison groups">
      <a href="#dense-sounds">New dense set · 14–19</a>
      <a href="#original-sound">Original · 13</a>
      <a href="#earlier-sounds">Earlier samples · 1–12</a>
      <a href="/original-wood-player.html">Exact original four-tap player</a>
    </nav>
    <section id="dense-sounds" aria-label="New dense wood samples">
      <h2>Dense, solid contacts</h2>
      <p className="sound-lab-note">Six treatments of the supplied original contact: less resonance, a shorter damped finish,
        and comparable impact energy near the quiet prototype. No added ringing or reverb.</p>
      <div className="sound-grid">{denseSamples.map(card)}</div>
    </section>
    <section id="original-sound" aria-label="Supplied original prototype">
      <h2>The unchanged original</h2><div className="sound-grid">{card(originalPrototype)}</div>
    </section>
    <section id="earlier-sounds" aria-label="Earlier wood samples">
      <h2>Earlier samples · kept for comparison</h2><div className="sound-grid">{woodSamples.map(card)}</div>
    </section>
    <p className="sound-lab-note" aria-live="polite">{last === null ? "Choose any sample to begin."
      : `Last requested: Sound ${last}. Try it again or compare another number.`}</p>
    <p className="sound-lab-note">Original synthesized contacts; no recordings copied from another chess app.
      Device speakers and volume affect what you hear.</p>
  </main>;
}

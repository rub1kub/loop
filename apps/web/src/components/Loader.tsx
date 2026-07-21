export function Loader() {
  return (
    <main className="loader" aria-label="LOOP загружается">
      <svg className="loader-mark" viewBox="0 0 220 120" role="img" aria-hidden="true">
        <path
          className="loader-base"
          d="M110 60C82 15 60 14 38 24 10 37 10 83 38 96c22 10 44 9 72-36 28 45 50 46 72 36 28-13 28-59 0-72-22-10-44-9-72 36Z"
        />
        <path
          className="loader-flow"
          d="M110 60C82 15 60 14 38 24 10 37 10 83 38 96c22 10 44 9 72-36 28 45 50 46 72 36 28-13 28-59 0-72-22-10-44-9-72 36Z"
        />
      </svg>
    </main>
  );
}

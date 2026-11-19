export function ErrorBox({
  text,
  retry,
}: {
  text: string;
  retry?: () => void;
}) {
  return (
    <div className="error" role="alert">
      {text}
      {retry && (
        <button className="text-button" onClick={retry}>
          Попробовать снова
        </button>
      )}
    </div>
  );
}

import parallel

STATE_EMPTY = 0
STATE_LOADED = 1

CMD_LOAD = (0, 1)  # (folderpath) -> None
CMD_STATE = (2, 3)  # () -> STATE
CMD_GENERATE = (4, 5)  # (pretty_midi.PrettyMIDI, batch_count) -> List[pretty_midi.PrettyMIDI]
CMD_EXIT = (6, 7)  # () -> bool


class CoconetJob(parallel.ParallelJob):
    def __init__(self):
        super().__init__()
        self._model = None

    def work(self, receiver: parallel.ChannelActor):
        import pretty_midi

        state = STATE_EMPTY
        action = receiver.invoked(*CMD_EXIT)
        while not action:
            action = receiver.invoked(*CMD_LOAD)
            if action:
                if self._model is not None:
                    del self._model
                    state = STATE_EMPTY

                print("[Coconet]: Loading", action.parameter)
                from magenta.models.coconet.coconet_sample import TFGenerator
                self._model = TFGenerator(action.parameter)
                state = STATE_LOADED
                action.finish()
                print("[Coconet]: Loaded", action.parameter)

            action = receiver.invoked(*CMD_GENERATE)
            if action:
                if self._model is None:
                    action.fail("No model is loaded.")
                elif not isinstance(action.parameter[0], pretty_midi.PrettyMIDI):
                    action.fail("Invalid parameter.")
                else:
                    print("[Coconet]: Generating voices...")
                    output = self._model.run_generation(
                        gen_batch_size=action.parameter[1],
                        piece_length=16,
                        total_gibbs_steps=96,
                        temperature=0.99
                    )
                    action.finish(output)
                    print("[Coconet]: Generated voices.")

            action = receiver.invoked(*CMD_STATE)
            if action:
                print("[Coconet]: State requested:", state)
                action.finish(state)
                print("[Coconet]: State sent.")
            action = receiver.invoked(*CMD_EXIT)

        print("[Coconet]: Exiting.")
        action.finish(True)

    def shutdown(self):
        self.channel.sender.invoke(*CMD_EXIT)
        self.join()
